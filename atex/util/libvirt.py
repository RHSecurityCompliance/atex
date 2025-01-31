import importlib


def import_libvirt():
    try:
        libvirt = importlib.import_module("libvirt")
    except ModuleNotFoundError:
        raise ModuleNotFoundError(
            "No module named 'libvirt', you need to install it from the package"
            " manager of your distro, ie. 'dnf install python3-libvirt' as it"
            " requires distro-wide headers to compile. It won't work from PyPI."
            " If using venv, create it with '--system-site-packages'.",
        ) from None

    # suppress console error printing, behave like a good python module
    libvirt.registerErrorHandler(lambda _ctx, _err: None, None)

    return libvirt
