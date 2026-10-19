"""Agent Analytics API methods for /chatReport (formerly dashboard).

This module owns the current /chatReport endpoints and their predecessors.
"""


class DashboardMixin:
    """Methods for the /chatReport and related Agent Analytics API family."""

    def _chat_report_filter(self, start_date, end_date, bot_id=None,
                            touch_point=None, intent_id=None, agent_id=None):
        """Build the date-string JSON body used by /api_v2/as_bot/chat-report/*."""
        if not start_date or not end_date:
            raise ValueError("chat-report queries require start_date and end_date (YYYY-MM-DD)")
        data = {
            "startDate": start_date,
            "endDate": end_date,
        }
        if bot_id is not None:
            data["botId"] = int(bot_id)
        if touch_point:
            data["touchPoint"] = touch_point
        if intent_id is not None:
            data["intentId"] = int(intent_id)
        if agent_id is not None:
            data["agentId"] = int(agent_id)
        return data

    def chat_report(self, endpoint, start_date, end_date, bot_id=None,
                    touch_point=None, intent_id=None, agent_id=None):
        """POST /api_v2/as_bot/chat-report/{endpoint} for modern /chatReport page metrics."""
        allowed = (
            "tickets",
            "messages",
            "intents",
            "agents",
            "satisfaction",
            "first-response",
            "return-retention",
            "inspection-results",
        )
        if endpoint not in allowed:
            raise ValueError(f"unknown chat-report endpoint: {endpoint}, allowed: {allowed}")
        payload = self._chat_report_filter(
            start_date, end_date, bot_id, touch_point, intent_id, agent_id
        )
        return self._curl(
            "POST", f"/api_v2/as_bot/chat-report/{endpoint}",
            data=payload,
            referer_path="/chatReport",
        )

    def chat_report_inbox_scripts(self):
        """GET /api_v2/as_bot/chat-report/inbox-scripts."""
        return self._curl(
            "GET", "/api_v2/as_bot/chat-report/inbox-scripts",
            referer_path="/chatReport",
        )

    def dashboard(self, metric, start_date, end_date, bot_id=None, channel=None,
                  business_type=None, granularity=None, agent_id=None):
        """GET an Agent Dashboard metric (the default Agent Analytics source)."""
        endpoints = {
            "overview": "overview",
            "message-trend": "message-trend",
            "intent-distribution": "intent-distribution",
            "agent-performance": "agent-performance",
            "intent-trend": "intent-trend",
            "agent-trend": "agent-trend",
            "handoff-heatmap": "handoff-heatmap",
            "turn-funnel": "turn-funnel",
        }
        try:
            suffix = endpoints[metric]
        except KeyError as exc:
            raise ValueError(f"unknown dashboard metric: {metric}") from exc
        return self._curl(
            "GET", f"/api_v2/as_bot/chat-dashboard/{suffix}",
            query_params=self._dashboard_filter(
                start_date, end_date, bot_id, channel, business_type,
                granularity, agent_id),
            referer_path="/dashboard",
        )

    def dashboard_handoff_chat_ids(self, week_start_date, primary_reason,
                                   secondary_reason, limit=None):
        """Get chat IDs for an Agent Dashboard handoff heatmap drilldown."""
        if not week_start_date or not primary_reason or not secondary_reason:
            raise ValueError("handoff chat IDs require week_start_date, primary_reason and secondary_reason")
        params = {
            "weekStartDate": week_start_date,
            "primaryReason": primary_reason,
            "secondaryReason": secondary_reason,
        }
        if limit is not None:
            params["limit"] = int(limit)
        return self._curl(
            "GET", "/api_v2/as_bot/chat-dashboard/handoff-heatmap/chat-ids",
            query_params=params, referer_path="/dashboard",
        )
