"""Rewrite only owner-authorized session resource URLs at the client boundary."""


def conversation_resource_urls(value, session_id, *, app=False):
    canonical = f"/api/sessions/{session_id}/resources/"
    mobile = f"/api/social/app/sessions/{session_id}/resources/"
    if isinstance(value, str):
        return value.replace(canonical, mobile) if app else value.replace(mobile, canonical)
    if isinstance(value, list):
        return [conversation_resource_urls(item, session_id, app=app) for item in value]
    if isinstance(value, dict):
        return {key: conversation_resource_urls(item, session_id, app=app) for key, item in value.items()}
    return value
