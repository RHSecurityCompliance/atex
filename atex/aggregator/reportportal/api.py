import datetime
import json
import ssl

import urllib3


class APIError(Exception):
    pass


class ReportPortalAPI:
    """
    - `url` is a ReportPortal instance URL.

    - `project` is an existing project name inside the RP instance.

    - `token` is a ReportPortal API token.

    - `ssl_verify` toggles whether to ignore insecure SSL/TLS RP connection.

      Useful for self-hosted instances.
    """

    def __init__(self, url, project, token, *, ssl_verify=True):
        self.url = url.strip("/")
        self.project = project
        self._api_v1 = f"{self.url}/api/v1/{project}"
        self._api_v2 = f"{self.url}/api/v2/{project}"
        self.token = token

        pool_kwargs = {
            "maxsize": 10,
            "block": True,
            "retries": urllib3.Retry(
                total=130,
                # account for API restarts / outages (up to ~4 hours),
                # start with quick retries (2s, 4s, 8s, ..) and settle at 2min
                backoff_factor=2,
                backoff_max=120,
                # retry on API server errors too, not just connection issues
                status_forcelist={408,429,500,502,503,504},
                # retry POST as well, even if risky
                allowed_methods=urllib3.Retry.DEFAULT_ALLOWED_METHODS | {"POST"},
            ),
        }
        if not ssl_verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            pool_kwargs["ssl_context"] = ctx
        self._http = urllib3.PoolManager(**pool_kwargs)

    def _query(self, method, url_part, *, api_url=None, **kwargs):
        api_url = api_url or self._api_v2
        loc = f"{api_url}{url_part}"

        reply = self._http.request(
            method, loc, headers={"Authorization": f"Bearer {self.token}"}, **kwargs,
        )

        if reply.status not in (200, 201):
            raise APIError(f"got HTTP {reply.status} on {method} {loc}: {reply.data}")

        if not reply.headers.get("Content-Type", "").startswith("application/json"):
            raise APIError(f"HTTP {reply.status} on {method} {loc} is not application/json")

        try:
            decoded = reply.json()
        except json.decoder.JSONDecodeError:
            raise APIError(f"failed to decode JSON for {method} {loc}: {reply.data}") from None

        return decoded

    @staticmethod
    def _now():
        return datetime.datetime.now(datetime.UTC).isoformat()

    def __str__(self):
        return f"{self.url} ({self.project})"

    def launch_start(self, name=None, rerun_of=None, **kwargs):
        """
        Start a RP launch.

        - `name` is the launch name.

        - `rerun_of` is an UUID of an existing launch to rerun.

          This ignores `name`.

        - `kwargs` are passed directly to the API.
        """
        if rerun_of:
            body = {
                "name": rerun_of,  # ignored, any unique string would work
                "rerun": True,
                "rerunOf": rerun_of,
            }
        else:
            if not name:
                raise ValueError("'name' must be given for non-reruns")
            body = {"name": name}
        body |= kwargs
        if "startTime" not in body:
            body["startTime"] = self._now()
        reply = self._query("POST", "/launch", json=body)
        return reply["id"]

    def launch_finish(self, launch_uuid, **kwargs):
        """
        Finish a RP launch.

        - `launch_uuid` is the launch UUID.

        - `kwargs` are passed directly to the API.
        """
        body = kwargs
        if "endTime" not in body:
            body["endTime"] = self._now()
        self._query("PUT", f"/launch/{launch_uuid}/finish", json=body)

    def item_start(self, launch_uuid, item_type, item_name, parent=None, **kwargs):
        """
        Start a launch item (suite, test or step).

        - `launch_uuid` is the parent launch UUID.

        - `item_type` is either `suite`, `test` or `step`.

        - `item_name` is the associated name.

        - `parent`, if given, specifies the parent item UUID to create
          the new item under.

        - `kwargs` are passed directly to the API.
        """
        body = {
            "launchUuid": launch_uuid,
            "type": item_type,
            "name": item_name,
        }
        body |= kwargs
        if "startTime" not in body:
            body["startTime"] = self._now()
        path = f"/item/{parent}" if parent else "/item"
        reply = self._query("POST", path, json=body)
        return reply["id"]

    def item_finish(self, launch_uuid, item_uuid, **kwargs):
        """
        Finish a launch item (suite, test or step).

        - `launch_uuid` is the launch UUID.

        - `item_uuid` is the item UUID to finish.

        - `kwargs` are passed directly to the API.
        """
        body = {"launchUuid": launch_uuid}
        body |= kwargs
        if "endTime" not in body:
            body["endTime"] = self._now()
        self._query("PUT", f"/item/{item_uuid}", json=body)

    def launch_get(self, launch_uuid):
        """
        Return full details (dict) for a given launch UUID.
        """
        return self._query("GET", f"/launch/uuid/{launch_uuid}", api_url=self._api_v1)

    def launch_list(self, *, page_size=50, max_pages=None):
        """
        Yield details (dicts) about launches in the project, most recent first.

        - `page_size` and `max_pages` control how many items to return at most.
        """
        page = 1
        while True:
            data = self._query(
                "GET", f"/launch?page.page={page}&page.size={page_size}"
                        "&page.sort=startTime,desc",
                api_url=self._api_v1,
            )
            yield from data.get("content") or ()
            total_pages = data.get("page", {}).get("totalPages") or 1
            if page >= total_pages or (max_pages is not None and page >= max_pages):
                break
            page += 1

    def item_get(self, item_uuid):
        """
        Return full details (dict) for a given item UUID.
        """
        return self._query("GET", f"/item/uuid/{item_uuid}", api_url=self._api_v1)

    def item_list(
        self, launch_id, parent_id=None, *,
        item_type=None, name=None, statuses=None, issue_types=None,
        page_size=50, max_pages=None,
    ):
        """
        Yield details (dicts) about items (suite, test, step) in the project.

        - `launch_id` is an internal RP database ID of the launch.

          If you have just UUID, use `.launch_get(launch_uuid)` and extract `id`
          from the returned dict. That is the internal ID.

        - `parent_id` is an internal RP database ID of the parent.

          If you have just UUID, use `.item_get(parent_uuid)` and extract `id`
          from the returned dict.

        - `item_type` is either `suite`, `test` or `step`.

        - `name` is the (visible) name of the item.

        - `statuses` are a sequence (list) of item statuses to search for.

          Ie. `passed`, `failed` or `interrupted`.

        - `issue_types` are a sequence (list) of issue type IDs to search for.

          Ie. `ti001` for "To Investigate", `nd001` for "No Defect", etc.

        - `page_size` and `max_pages` control how many items to return at most.
        """
        filters = {
            "filter.eq.launchId": launch_id,
            "filter.eq.parentId": parent_id,
            "filter.in.status": ",".join(statuses) if statuses else None,
            "filter.in.issueType": ",".join(issue_types) if issue_types else None,
            "filter.eq.type": item_type,
            "filter.eq.name": name,
        }
        fields = {k: v for k, v in filters.items() if v is not None}
        fields["page.size"] = page_size
        page = 1
        while True:
            fields["page.page"] = page
            data = self._query("GET", "/item", fields=fields, api_url=self._api_v1)
            yield from data.get("content") or ()
            total_pages = data.get("page", {}).get("totalPages") or 1
            if page >= total_pages or (max_pages is not None and page >= max_pages):
                break
            page += 1

    def log_upload(self, launch_uuid, item_uuid, logs):
        """
        - `launch_uuid` is the launch UUID.

        - `item_uuid` is the item UUID to associate the logs with.

        - `logs` is an iterable of dicts, each with:

          - `message` is a string which can hold either a short description
            or the log content itself.

            It's always displayed inline on the page itself.

          - `level` is a string like INFO or ERROR with the log level.

          - `file` as an optional dict specifying an attachment for the log.

            Attachments are linked from the UI page, they are never inlined,
            and can be used for text or binary data. It is recommended to keep
            the `message` short (brief description) in this case, not the actual
            large contents.

            If given, the dict must contain:

            - `name` is a string with the file name of the attachment.
            - `content` is a bytes object of the raw attachment data.
            - `content_type` is a string with MIME type of the attachment.
        """
        now = self._now()

        json_entries = []
        fields = []
        for log in logs:
            entry = {
                "launchUuid": launch_uuid,
                "itemUuid": item_uuid,
                "time": now,
                "level": log["level"],
                "message": log["message"],
            }

            if attachment := log.get("file"):
                entry["file"] = {"name": attachment["name"]}
                attach_field = urllib3.fields.RequestField(
                    name=attachment["name"],
                    data=attachment["content"],
                    filename=attachment["name"],
                )
                attach_field.make_multipart(content_type=attachment["content_type"])
                fields.append(attach_field)

            json_entries.append(entry)

        json_field = urllib3.fields.RequestField(
            name="json_request_part",
            data=json.dumps(json_entries),
        )
        json_field.make_multipart(content_type="application/json")
        fields.append(json_field)

        self._query("POST", "/log", fields=fields)
