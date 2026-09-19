PLUGIN = {
    "name": "example",
    "version": "0.1.0",
    "description": "Example Runner plugin for testing the plugin API.",
    "hooks": ["on_match_finished"],
}


def on_match_finished(context):
    return {"ok": True, "match_id": context.get("match_id")}
