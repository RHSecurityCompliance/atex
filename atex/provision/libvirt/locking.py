"""
Helpers for "reserving" (locking) libvirt domains using the <metadata> tag.

The idea is for each user to generate some "signature" (ie. UUIDv4) and
attempt to lock eligible domains on a libvirt host in a random order,
hopefully eventually succeeding (as others release the domain locks).

Lock safety is ensured by libvirt retaining <metadata> content (tag) order,
so each user can re-check (after locking) whether the race was won or lost,
depending on whether the user's signature is on top of <metadata>.

A timestamp (meaning now()+duration) is used as the lock tag value/text,
and any expired timestamps (now() > timestamp) are ignored by the locking
logic.
"""

import re
import time
import random
import xml.etree.ElementTree as ET

import libvirt


def get_locks(domain, expired=False):
    """
    Yield (signature,timestamp) tuples of atex-lock entries for a 'domain'.

    If 'expired' is True, yield also locks with an expired timestamp.

    If a timestamp is missing, it is substituted with 0.
    """
    xml_dump = ET.fromstring(domain.XMLDesc(libvirt.VIR_DOMAIN_XML_INACTIVE))
    metadata = xml_dump.find("metadata")
    # no <metadata> - no locks possible
    if metadata is None:
        return
    now = int(time.time())
    for elem in metadata:
        if match := re.fullmatch(r"{(.+)}atex-lock", elem.tag):
            timestamp = int(elem.text) if elem.text else 0
            if not expired and timestamp <= now:
                continue
            signature = match.group(1)
            yield (signature, timestamp)


def unlock(domain, signature):
    """
    Unlock a domain previously locked by lock().
    """
    domain.setMetadata(
        libvirt.VIR_DOMAIN_METADATA_ELEMENT,
        None,
        "atex-lock",
        str(signature),
        libvirt.VIR_DOMAIN_AFFECT_CONFIG,
    )


def lock(domain, signature, timestamp):
    """
    Attempt to lock a domain under 'signature' ownership,
    writing out 'timestamp' as the lock tag content.

    Returns True if the domain was successfully locked, False otherwise.
    """
    signature = str(signature)
    timestamp = int(timestamp)

    # if there are any existing locks held on the domain
    if any(get_locks(domain)):
        return False

    # try locking it
    domain.setMetadata(
        libvirt.VIR_DOMAIN_METADATA_ELEMENT,
        f"<atex-lock>{timestamp}</atex-lock>",
        "atex-lock",
        signature,
        libvirt.VIR_DOMAIN_AFFECT_CONFIG,
    )

    # get fresh XML and verify we won the race
    try:
        first = next(get_locks(domain))
    except StopIteration:
        raise RuntimeError(
            "failed to verify lock signature, was timestamp already expired?",
        ) from None

    first_sig, first_stamp = first
    if first_sig == signature and first_stamp == timestamp:
        return True
    else:
        # we lost
        unlock(domain, signature)
        return False


def lock_any(connection, signature, duration, filter_domains=lambda _: True):
    """
    Given a libvirt 'connection', attempt to lock (reserve) any one
    domain under 'signature' ownership for 'duration' seconds.

    If 'filter_domain' is given as a callable, it is used to filter
    domains considered for locking. It takes one argument (libvirt
    domain object) and must return True (domain is eligible for locking)
    or False (domain should be skipped).
    For example: lambda dom: dom.name().startswith("foo-")

    Returns a libvirt domain object of a successfully locked domain,
    or None if no domain could be locked.
    """
    domains = connection.listAllDomains(libvirt.VIR_CONNECT_LIST_DOMAINS_PERSISTENT)
    # try to avoid lock conflicts
    random.shuffle(domains)

    timestamp = int(time.time() + duration)
    for domain in filter(filter_domains, domains):
        if lock(domain, signature, timestamp):
            return domain
    return None


def unlock_all(connection, signature=None, shutdown=False, filter_domains=lambda _: True):
    """
    Remove all locks for all domains.

    If 'signature' is given, remove only locks matching the signature.

    If 'shutdown' is True, also forcibly shutdown (destroy) all domains.

    If 'filter_domains' is given, it behaves like for lock_any().
    """
    domains = connection.listAllDomains(libvirt.VIR_CONNECT_LIST_DOMAINS_PERSISTENT)
    for domain in filter(filter_domains, domains):
        for lock, _ in get_locks(domain, expired=True):
            if signature:
                if str(signature) == lock:
                    unlock(domain, lock)
            else:
                unlock(domain, lock)
        if shutdown:
            domain.destroy()


def cleanup_expired(connection, timestamp=None, filter_domains=lambda _: True):
    """
    Clean up expired locks for all domains.

    Useful when a client terminates without releasing the lock, which later
    expires (making the domain available), but as no other user is responsible
    for the given signature, it is never removed, unless this function is used
    (by some maintenance service).

    Note that unlock_all() cleans up all locks, incl. expired ones.

    If 'timestamp' is given, it is used instead of the now() UTC timestamp.

    If 'filter_domains' is given, it behaves like for lock_any().
    """
    now = int(timestamp) if timestamp is not None else int(time.time())
    domains = connection.listAllDomains(libvirt.VIR_CONNECT_LIST_DOMAINS_PERSISTENT)
    for domain in filter(filter_domains, domains):
        for signature, stamp in get_locks(domain, expired=True):
            if stamp <= now:
                unlock(domain, signature)
