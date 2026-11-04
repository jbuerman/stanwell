"""Constants used by the Toggl integration."""

API_URL = "https://api.track.toggl.com/api/v9/me/time_entries"
REPORTS_API_URL = (
    "https://api.track.toggl.com/reports/api/v3/"
    "workspace/{workspace_id}/search/time_entries"
)
PROJECTS_API_URL = (
    "https://api.track.toggl.com/api/v9/" "workspaces/{workspace_id}/projects"
)
RECENT_ENTRY_WINDOW_DAYS = 85
WORKSPACES_API_URL = "https://api.track.toggl.com/api/v9/me/workspaces"
