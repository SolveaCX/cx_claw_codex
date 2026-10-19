"""SolveaClient — Solvea Bot Backend API client (library only, no CLI).

Import example:
    from client import SolveaClient
    c = SolveaClient()          # prod (SOLVEA_PROD_TOKEN)
    c = SolveaClient(env="staging")

Environment variables:
    SOLVEA_ENV          - "prod" (default) or "staging"
    SOLVEA_TOKEN        - staging JWT token
    SOLVEA_PROD_TOKEN   - production JWT token
    SOLVEA_BASE_URL     - staging base URL (default: https://apps-staging.voc.ai)
    SOLVEA_PROD_URL     - production base URL (default: https://apps.voc.ai)
    SOLVEA_PROJECT_ID   - project ID (auto-detected if omitted)
"""

import json
import mimetypes
import os
import time
import unicodedata
from urllib.parse import quote

import httpx

from dashboard import DashboardMixin


class SolveaClient(DashboardMixin):
    """Client for Solvea Bot Backend API.

    Dual-environment:
      - prod (default): base_url=https://apps.voc.ai, cookie=_token
      - staging:        base_url=https://apps-staging.voc.ai, cookie=_token_staging
    """

    def __init__(self, token=None, base_url=None, project_id=None, env=None):
        if env is None:
            env = os.environ.get("SOLVEA_ENV", "prod")
        self.env = env
        if env == "prod":
            self.token = token or os.environ.get("SOLVEA_PROD_TOKEN", "") or os.environ.get("SOLVEA_TOKEN", "")
            self.base_url = (base_url or os.environ.get("SOLVEA_PROD_URL", "https://apps.voc.ai")).rstrip("/")
            self._cookie_name = "_token"
            self._qam_prefix = "/api_v2/qam"
        else:
            self.token = token or os.environ.get("SOLVEA_TOKEN", "")
            self.base_url = (base_url or os.environ.get("SOLVEA_BASE_URL", "https://apps-staging.voc.ai")).rstrip("/")
            self._cookie_name = "_token_staging"
            self._qam_prefix = "/sns_v1"
        self._project_id = project_id or os.environ.get("SOLVEA_PROJECT_ID", "")
        self._bot_id = None

    @staticmethod
    def _request_with_retry(method, url, **kwargs):
        """Bound external calls to connect<=3s/read<=30s and two retries."""
        timeout = httpx.Timeout(30.0, connect=3.0)
        last_error = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=timeout) as client:
                    return client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(0.2 * (2 ** attempt))
        raise last_error

    @property
    def internal_url(self):
        if self.env == "prod":
            return "https://internal.shulex.com"
        return self.base_url

    def _curl(self, method, path, data=None, query_params=None, referer_path="/chatbot"):
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}{referer_path}",
            "Cookie": f"{self._cookie_name}={self.token}",
        }
        resp = self._request_with_retry(
            method, url,
            params=query_params,
            headers=headers,
            json=data,
        )
        return self._parse_response(resp, method, path)

    def _curl_internal(self, method, path, data=None, query_params=None):
        url = f"{self.internal_url}{path}"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "x-language": "cn",
            "x-token-domain": ".shulex.com",
            "Cookie": f"{self._cookie_name}={self.token}",
            "Origin": self.internal_url,
            "Referer": f"{self.internal_url}/chatbot",
        }
        resp = self._request_with_retry(
            method, url,
            params=query_params,
            headers=headers,
            json=data,
        )
        return self._parse_response(resp, method, path)

    def _download(self, path, target_path, query_params=None, referer_path="/chatbot"):
        """Download a non-JSON response from the web backend to target_path."""
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "*/*",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}{referer_path}",
            "Cookie": f"{self._cookie_name}={self.token}",
        }
        resp = self._request_with_retry("GET", url, params=query_params, headers=headers)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code} GET {path}: {resp.text}")
        target_path = os.fspath(target_path)
        os.makedirs(os.path.dirname(os.path.abspath(target_path)) or ".", exist_ok=True)
        with open(target_path, "wb") as f:
            f.write(resp.content)
        return target_path

    def _parse_response(self, resp, method, path):
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw": resp.text}

        if resp.status_code >= 400:
            error = json.dumps(payload, ensure_ascii=False)
            raise RuntimeError(f"HTTP {resp.status_code} {method} {path}: {error}")

        if isinstance(payload, dict):
            for key in ("code", "errno"):
                if key in payload and payload.get(key) not in (None, 0, "0", 200, "200", "OK", "SUCCESS"):
                    message = payload.get("msg") or payload.get("message") or payload.get("error") or payload
                    raise RuntimeError(f"API error {method} {path}: {message}")
            if payload.get("success") is False:
                message = payload.get("msg") or payload.get("message") or payload.get("error") or payload
                raise RuntimeError(f"API error {method} {path}: {message}")

        return payload

    @property
    def project_id(self):
        if not self._project_id:
            info = self.get_project_info()
            if info and len(info) > 0:
                self._project_id = str(info[0].get("projectId", 950))
                self._bot_id = str(info[0].get("id", ""))
            else:
                self._project_id = "950"
        return self._project_id

    @property
    def bot_id(self):
        if not self._bot_id:
            info = self.get_project_info()
            if info and len(info) > 0:
                self._bot_id = str(info[0].get("id", "723"))
                self._project_id = str(info[0].get("projectId", 950))
            else:
                self._bot_id = "723"
        return self._bot_id

    # ── Project ──

    def get_project_info(self):
        """GET /api_v2/gpt/bots — get projectId and botId."""
        return self._curl("GET", "/api_v2/gpt/bots")

    # ── Mock data ──

    @staticmethod
    def _validate_mock_type(mock_type):
        """Validate a mock type before using it as an API identifier or path segment."""
        if not isinstance(mock_type, str) or not mock_type:
            raise ValueError("mock_type must be a non-empty string")
        if mock_type in (".", ".."):
            raise ValueError("mock_type must be a safe path segment")
        if any(char in "/\\?#%" or unicodedata.category(char) == "Cc" for char in mock_type):
            raise ValueError("mock_type must be a safe path segment")
        return mock_type

    def replace_mock_data(self, mock_type, records):
        """Replace all records for one mock data type."""
        mock_type = self._validate_mock_type(mock_type)
        if not isinstance(records, list):
            raise ValueError("records must be a list")
        if len(records) > 10000:
            raise ValueError("records must contain at most 10000 records")
        return self._curl(
            "POST",
            f"/api_v2/gpt/mockdata/reAddMockData/{quote(mock_type, safe='')}",
            data=records,
        )

    def query_mock_data(self, mock_type):
        """Query project-scoped records for one mock data type."""
        mock_type = self._validate_mock_type(mock_type)
        return self._curl(
            "GET",
            "/api_v2/gpt/mockdata/queryMockData",
            query_params={"type": mock_type, "globalData": "false"},
        )

    # ── Transcript (单条详情) ──

    def get_transcript(self, chat_id, is_compare=True):
        """GET /api_v2/gpt/project/{projectId}/transcript/{chatId}?isCompare=true

        获取单条会话记录详情；is_compare=true 时同时返回历史上下文与当前资源的比较结果。
        """
        query = {"isCompare": "true"} if is_compare else None
        return self._curl(
            "GET",
            f"/api_v2/gpt/project/{self.project_id}/transcript/{chat_id}",
            query_params=query,
        )

    def get_chat_context(self, bot_id, data):
        """POST /api_v2/gpt/bot/{botId}/chat/context/compare

        比较已保存的轮次上下文与当前资源状态，不会重新执行该轮对话。
        data 必须是消息中保存的完整 ChatContext（dict）。
        """
        return self._curl(
            "POST",
            f"/api_v2/gpt/bot/{bot_id}/chat/context/compare",
            data=data,
        )

    # ── Agents ──

    def list_agents(self, category="text", no_meta=True):
        """POST queryAgent — list all agents."""
        return self._curl("POST", "/api_v2/gpt/ap/queryAgent", {
            "projectId": int(self.project_id),
            "needRelation": True,
            "noMeta": no_meta,
            "category": category,
        })

    def get_agent(self, agent_id):
        """POST queryAgent with agentId — full agent detail.

        Note: CHAT_FLOW agents do not return chatFlowGraph here (by design).
        Use get_chatflow_graph(agent_id) to read the graph, update_chatflow() to
        update an existing graph, or deploy_chatflow() to create a new agent.
        """
        return self._curl("POST", "/api_v2/gpt/ap/queryAgent", {
            "projectId": int(self.project_id),
            "agentId": int(agent_id),
            "needRelation": True,
            "squareAgent": False,
        })

    def get_chatflow_graph(self, agent_id):
        """POST chatflow/queryGraph/latest — get the latest chatFlowGraph for a CHAT_FLOW agent.

        Returns the graph (nodes / edges / viewport) used by the agent at runtime.
        Pair with update_chatflow() for existing-agent edits.
        """
        return self._curl(
            "POST",
            "/api_v2/gpt/chatflow/queryGraph/latest",
            {"agentId": int(agent_id)},
        )

    def create_agent(self, data):
        """POST createAgent — create a new agent. projectId auto-filled if missing."""
        if "projectId" not in data:
            data["projectId"] = int(self.project_id)
        return self._curl("POST", "/api_v2/gpt/ap/createAgent", data)

    def update_agent(self, data):
        """POST updateAgent — full object update (agentId required).
        Always query first (get_agent) to get the full object before calling this.
        When changing prompt, also update displayPrompt to keep them in sync.
        """
        if "agentId" not in data and "id" in data:
            data["agentId"] = data["id"]
        return self._curl("POST", "/api_v2/gpt/ap/updateAgent", data)

    def update_chatflow(self, agent_id, graph, publish=False):
        """Update an existing CHAT_FLOW agent graph.

        Default behavior matches the UI autosave path: save as the current
        user's draft. Pass publish=True only when the user explicitly confirms
        this version should go live.
        """
        agent_detail = self.get_agent(agent_id)
        agent = agent_detail[0] if isinstance(agent_detail, list) else agent_detail
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        if agent.get("type") != "CHAT_FLOW":
            raise ValueError(f"Agent {agent_id} is not CHAT_FLOW")
        if (
            not isinstance(graph, dict)
            or not isinstance(graph.get("nodes"), list)
            or not isinstance(graph.get("edges"), list)
        ):
            raise ValueError("chatFlowGraph must be a dict with nodes and edges")

        payload = dict(agent)
        payload["agentId"] = payload.get("id") or int(agent_id)
        payload["meta"] = dict(payload.get("meta") or {})
        payload["meta"]["chatFlowGraph"] = graph

        if publish:
            payload.pop("backupType", None)
            payload["meta"].pop("backupType", None)
            payload["meta"].pop("draft_flow_updatetime", None)
        else:
            payload["backupType"] = "DRAFT"
            payload["meta"]["draft_flow_updatetime"] = int(time.time() * 1000)

        result = self.update_agent(payload)
        if isinstance(result, dict) and result.get("errno") not in (None, 0, "0"):
            error = json.dumps(result, ensure_ascii=False)
            raise RuntimeError(f"update_chatflow failed: {error}")
        return result

    # ── Tools / Plugins ──

    def list_plugins(self):
        """POST queryPlugin — list available tools."""
        return self._curl("POST", "/api_v2/gpt/ap/queryPlugin", {
            "projectId": int(self.project_id),
            "needRelation": False,
        })

    def list_chatflow_plugins(self, for_agent_node=True):
        """List tools using the same catalog and visibility rules as Chatflow PE."""
        return self._curl("POST", "/api_v2/gpt/chatflow/queryPlugin", {
            "projectId": int(self.project_id),
            "forAgentNode": bool(for_agent_node),
        })

    def get_plugin(self, plugin_id):
        """POST queryPlugin with pluginId — get full tool detail."""
        return self._curl("POST", "/api_v2/gpt/ap/queryPlugin", {
            "projectId": int(self.project_id),
            "pluginId": int(plugin_id),
            "convertStrategyV5": True,
        })

    def create_plugin(self, data):
        """POST createPlugin — create a new tool."""
        data.setdefault("projectId", int(self.project_id))
        return self._curl("POST", "/api_v2/gpt/ap/createPlugin", data)

    def update_plugin(self, data):
        """POST updatePlugin — full object update (pluginId required)."""
        data.setdefault("projectId", int(self.project_id))
        if "pluginId" not in data and "id" in data:
            data["pluginId"] = data["id"]
        return self._curl("POST", "/api_v2/gpt/ap/updatePlugin", data)

    def delete_plugin(self, plugin_id):
        """POST deletePlugin — delete a plugin by ID."""
        return self._curl("POST", "/api_v2/gpt/ap/deletePlugin",
                          {"projectId": int(self.project_id), "pluginId": plugin_id})

    def run_http_plugin(self, config, request_body=None):
        """POST runHttpPlugin — test-run an HTTP plugin without saving."""
        if request_body is not None and not isinstance(request_body, dict):
            raise ValueError("request_body must be a JSON object")
        data = {
            "projectId": int(self.project_id),
            "botId": int(self.bot_id),
            "externalHttpCallConfig": config,
        }
        if request_body is not None:
            data["externalHttpCallRequestBody"] = request_body
        return self._curl("POST", "/api_v2/gpt/ap/runHttpPlugin", data)

    def build_plugin(self, plugin_id, request_body=None):
        """POST build/plugin — auto-generate response params from a test call."""
        data = {
            "projectId": int(self.project_id),
            "botId": int(self.bot_id),
            "pluginId": plugin_id,
        }
        if request_body:
            data["externalHttpCallRequestBody"] = request_body
        return self._curl("POST", f"/api_v2/gpt/ap/{self.project_id}/build/plugin", data)

    # ── AI Fields ──

    def list_ai_fields(self):
        """List fields exposed by the CHAT_FLOW canvas endpoint."""
        return self._curl("POST", "/api_v2/gpt/chatflow/queryAiFields", {})

    def list_agent_ai_fields(self):
        """List fields accepted by the frontend Agent field-range validation."""
        return self._curl(
            "POST",
            "/api_v2/gpt/field/list/range",
            {"fieldRange": ["all", "agent", "agent_preload_visible"]},
        )

    def create_ai_field(self, data):
        """POST createAiField — create an AI field."""
        data.setdefault("projectId", int(self.project_id))
        return self._curl("POST", "/api_v2/gpt/chatflow/createAiField", data)

    def update_ai_field(self, data):
        """POST updateAiField — full object update (aiFieldId required)."""
        data.setdefault("projectId", int(self.project_id))
        if "aiFieldId" not in data and "id" in data:
            data["aiFieldId"] = data["id"]
        return self._curl("POST", "/api_v2/gpt/chatflow/updateAiField", data)

    # ── Tars AI Field management ──

    def get_ai_field_guide_record(self):
        """Read the tenant's AI Field initialization state from Tars."""
        return self._curl("POST", "/api_v2/tars/api/field/manage/guide/record")

    def initialize_ai_fields(self):
        """Initialize Tars system-preinstalled AI Fields for the current tenant."""
        return self._curl("GET", "/api_v2/tars/api/field/manage/pre/install")

    def list_managed_ai_fields(self, page_index=1, page_size=50, name=""):
        """Page Tars-managed AI Fields, including custom fields and usage counts."""
        return self._curl("POST", "/api_v2/tars/api/field/manage/page", {
            "pageIndex": int(page_index),
            "pageSize": int(page_size),
            "name": name or "",
        })

    def get_managed_ai_field(self, field_id):
        """Read a Tars-managed AI Field definition by ID."""
        return self._curl("GET", f"/api_v2/tars/api/field/manage/detail/{int(field_id)}")

    def create_managed_ai_field(self, data):
        """Create a custom AI Field in Tars."""
        return self._curl("POST", "/api_v2/tars/api/field/manage/create", data)

    def update_managed_ai_field(self, data):
        """Update a Tars-managed AI Field definition."""
        return self._curl("POST", "/api_v2/tars/api/field/manage/update", data)

    def delete_managed_ai_field(self, field_id):
        """Delete an unused custom AI Field from Tars."""
        return self._curl("GET", f"/api_v2/tars/api/field/manage/delete/{int(field_id)}")

    def toggle_managed_ai_field(self, field_id):
        """Toggle a Tars-managed AI Field's enabled state."""
        return self._curl("GET", f"/api_v2/tars/api/field/manage/switch/{int(field_id)}")

    # ── AI quality inspection management ──

    def get_quality_inspection_status(self):
        """Read whether AI quality inspection is enabled for the current project."""
        return self._curl("GET", "/api_v2/intelli/inspection/ticket/status")

    def update_quality_inspection_status(self, enabled):
        """Enable or disable AI quality inspection for the current project."""
        return self._curl("POST", "/api_v2/intelli/inspection/ticket/open", {
            "open": bool(enabled),
            "projectId": int(self.project_id),
        })

    def list_quality_inspection_rules(self, begin_timestamp=None, end_timestamp=None):
        """List quality inspection rules and optional period hit statistics."""
        query_params = {}
        if begin_timestamp is not None:
            query_params["beginTimestamp"] = int(begin_timestamp)
        if end_timestamp is not None:
            query_params["endTimestamp"] = int(end_timestamp)
        return self._curl("GET", "/api_v2/intelli/inspection/ticket/rules",
                          query_params=query_params or None)

    def get_quality_inspection_rule(self, inspection_key):
        """Read a system quality rule's configuration."""
        return self._curl("GET", "/api_v2/intelli/inspection/ticket/rules/detail",
                          query_params={"inspectionKey": inspection_key})

    def update_quality_inspection_rule(self, data):
        """Update a system quality rule's scope, action, or enabled state."""
        return self._curl("POST", "/api_v2/intelli/inspection/ticket/rules", data)

    def create_custom_quality_rule(self, data):
        """Create a custom quality inspection rule."""
        return self._curl("POST", "/api_v2/intelli/inspection/ticket/customRules/create", data)

    def get_custom_quality_rule(self, inspection_key):
        """Read a custom quality inspection rule's full definition."""
        return self._curl("POST", "/api_v2/intelli/inspection/ticket/customRules/detail", {
            "inspectionKey": inspection_key,
        })

    def update_custom_quality_rule(self, data):
        """Update a custom quality inspection rule."""
        return self._curl("POST", "/api_v2/intelli/inspection/ticket/customRules/update", data)

    def delete_custom_quality_rule(self, inspection_key):
        """Delete a custom quality inspection rule."""
        return self._curl("POST", "/api_v2/intelli/inspection/ticket/customRules/delete", {
            "inspectionKey": inspection_key,
        })

    def list_quality_alert_rules(self):
        """List configured quality inspection alert rules."""
        return self._curl("GET", "/api_v2/intelli/inspection/alert/list")

    def get_quality_alert_rule(self, alert_id):
        """Read one quality inspection alert rule."""
        return self._curl("GET", "/api_v2/intelli/inspection/alert/detail",
                          query_params={"id": int(alert_id)})

    def create_quality_alert_rule(self, data):
        """Create a quality inspection alert rule."""
        return self._curl("POST", "/api_v2/intelli/inspection/alert/create", data)

    def update_quality_alert_rule(self, data):
        """Update a quality inspection alert rule."""
        return self._curl("POST", "/api_v2/intelli/inspection/alert/update", data)

    def delete_quality_alert_rule(self, alert_id):
        """Delete a quality inspection alert rule."""
        return self._curl("GET", "/api_v2/intelli/inspection/alert/delete",
                          query_params={"id": int(alert_id)})

    def list_quality_alert_messages(self, data):
        """Page quality inspection alert delivery messages."""
        return self._curl("POST", "/api_v2/intelli/inspection/alert/message/list", data)

    def get_quality_alert_message(self, message_id):
        """Read one quality inspection alert delivery message."""
        return self._curl("GET", "/api_v2/intelli/inspection/alert/message/detail",
                          query_params={"id": int(message_id)})

    # ── Chat ──

    def chat(self, message=None, bot_id=None, chat_id=None, touch_point="LIVE_CHAT",
             messages=None, metadata=None, option=None):
        """POST /api_v2/gpt/bot/{botId}/chat — 同步对话。

        metadata 可放任意键，常用：
          specified_agent_id   int    强制路由到指定 agent，绕策略匹配
          specified_agent_data dict   临时改 agent 配置不入库（调试用，本项目不主动用）
          业务字段                    customer_email / order_type / country / ...

        返回结构：{chatId, content, reason, context.{agent, ext.{chatflow_run_info,...}},
                  handoff, strategyName, type, ...}
        """
        bid = bot_id or self.bot_id
        data = {
            "botId": int(bid),
            "projectId": int(self.project_id),
            "touchPoint": touch_point,
            "option": option or {"debug": True},
        }
        if message is not None:
            data["message"] = message
        if messages is not None:
            data["messages"] = messages
        if chat_id:
            data["chatId"] = chat_id
        if metadata:
            data["metadata"] = metadata
        return self._curl("POST", f"/api_v2/gpt/bot/{bid}/chat", data)

    def chat_trace(self, message=None, bot_id=None, chat_id=None, touch_point="LIVE_CHAT",
                   messages=None, metadata=None, option=None):
        """Run synchronous chat with debug options and retain timing metadata."""
        merged_option = dict(option or {})
        merged_option["debug"] = True
        merged_option["verbose"] = True
        started_at = time.time()
        started_perf = time.perf_counter()
        action = self.chat(
            message=message,
            bot_id=bot_id,
            chat_id=chat_id,
            touch_point=touch_point,
            messages=messages,
            metadata=metadata,
            option=merged_option,
        )
        if not isinstance(action, dict) or not action:
            raise RuntimeError("synchronous chat returned no AgentAction")
        finished_at = time.time()
        elapsed_ms = round((time.perf_counter() - started_perf) * 1000)
        return {
            "action": action,
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_ms": elapsed_ms,
        }

    def chat_stream_action_trace(self, message=None, bot_id=None, chat_id=None,
                                 touch_point="LIVE_CHAT", messages=None, metadata=None,
                                 option=None, on_event=None):
        """Run stream chat while retaining only the final AgentAction and timing."""
        bid = bot_id or self.bot_id
        merged_option = dict(option or {})
        merged_option["debug"] = True
        merged_option["verbose"] = True
        body = {
            "botId": int(bid),
            "projectId": int(self.project_id),
            "touchPoint": touch_point,
            "option": merged_option,
        }
        if message is not None:
            body["message"] = message
        if messages is not None:
            body["messages"] = messages
        if chat_id:
            body["chatId"] = chat_id
        if metadata:
            body["metadata"] = metadata
        url = f"{self.base_url}/api_v2/gpt/bot/{bid}/chat/stream"
        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/chatbot",
            "Cookie": f"{self._cookie_name}={self.token}",
        }
        final_action = None
        started_at = time.time()
        started_perf = time.perf_counter()
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=3.0)) as client:
            with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status_code} POST /api_v2/gpt/bot/{bid}/chat/stream: "
                        f"{response.text}"
                    )
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload:
                        continue
                    try:
                        event = json.loads(payload)
                    except Exception:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if on_event is not None:
                        on_event(event)
                    if event.get("errno") not in (None, 0, "0"):
                        raise RuntimeError(
                            f"API error POST /api_v2/gpt/bot/{bid}/chat/stream: "
                            f"{event.get('errmsg') or event.get('message') or event.get('errno')}"
                        )
                    if not event.get("isEnd"):
                        continue
                    event_data = event.get("data")
                    if isinstance(event_data, dict):
                        final_action = event_data
                    elif any(key in event for key in ("chatId", "type", "handoff")):
                        final_action = {
                            key: value for key, value in event.items()
                            if key not in ("isEnd", "data", "agentExtraResponseParam")
                        }
        if not final_action:
            raise RuntimeError("stream chat returned no final AgentAction")
        finished_at = time.time()
        return {
            "action": final_action,
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_ms": round((time.perf_counter() - started_perf) * 1000),
        }

    def chat_stream(self, message=None, bot_id=None, chat_id=None, touch_point="LIVE_CHAT",
                    messages=None, metadata=None, option=None):
        """POST /api_v2/gpt/bot/{botId}/chat/stream — SSE 流式，聚合后返回最终 AgentAction。

        返回结构与 client.chat 同步对话一致：{chatId, content, reason (noReplyReason),
        context.{agent, ext.{chatflow_run_info, invoke_agent_name}}, handoff, strategyName,
        type, isEnd:True, ...}

        metadata 同 chat：可放 specified_agent_id / specified_agent_data /
                         业务字段（customer_email / order_type / ...）
        """
        bid = bot_id or self.bot_id
        url = f"{self.base_url}/api_v2/gpt/bot/{bid}/chat/stream"
        body = {
            "botId": int(bid),
            "projectId": int(self.project_id),
            "touchPoint": touch_point,
            "option": option or {"debug": True},
        }
        if message is not None:
            body["message"] = message
        if messages is not None:
            body["messages"] = messages
        if chat_id:
            body["chatId"] = chat_id
        if metadata:
            body["metadata"] = metadata
        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/chatbot",
            "Cookie": f"{self._cookie_name}={self.token}",
        }
        final_event = None
        parts = []
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=3.0)) as client:
            with client.stream("POST", url, headers=headers, json=body) as resp:
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload:
                        continue
                    try:
                        evt = json.loads(payload)
                    except Exception:
                        continue
                    if isinstance(evt, dict):
                        chunk = evt.get("content")
                        if chunk:
                            parts.append(chunk)
                        if evt.get("isEnd"):
                            final_event = evt
        if final_event is not None:
            return final_event
        return {"content": "".join(parts), "isEnd": True}

    def chat_async(self, message=None, bot_id=None, chat_id=None, touch_point="LIVE_CHAT",
                   messages=None, metadata=None, option=None,
                   callback=None, expire_minutes=None):
        """POST /api_v2/gpt/bot/{botId}/chat/async — 提交异步对话，返回 AsyncReceipt。

        AsyncReceipt: {receipt, expireAt, handoff, errorMessage}
        幂等键：chatId + 最后一条 USER message id。
        callback / expire_minutes 透传到 query string。
        """
        bid = bot_id or self.bot_id
        data = {
            "botId": int(bid),
            "projectId": int(self.project_id),
            "touchPoint": touch_point,
            "option": option or {"debug": True},
        }
        if message is not None:
            data["message"] = message
        if messages is not None:
            data["messages"] = messages
        if chat_id:
            data["chatId"] = chat_id
        if metadata:
            data["metadata"] = metadata
        query = {}
        if callback:
            query["callback"] = callback
        if expire_minutes is not None:
            query["expireMinutes"] = expire_minutes
        return self._curl(
            "POST",
            f"/api_v2/gpt/bot/{bid}/chat/async",
            data=data,
            query_params=query or None,
        )

    def get_async_result(self, receipt, bot_id=None):
        """GET /api_v2/gpt/bot/{botId}/chat/async/{receipt} — 轮询异步结果。

        AsyncResult: {completed, data (AgentAction), error}
        completed=True 时 data 与 chat_stream 返回一致；建议轮询 1-2s，过 expireAt 停。
        """
        bid = bot_id or self.bot_id
        return self._curl("GET", f"/api_v2/gpt/bot/{bid}/chat/async/{receipt}")

    # ── Intents ──

    def list_intents(self, category="E_COMMERCE"):
        """GET intents — list intents."""
        params = {"category": category} if category else {}
        return self._curl("GET", f"/api_v2/gpt/project/{self.project_id}/intents",
                          query_params=params)

    def create_intent(self, data):
        """POST intent — create a new intent."""
        return self._curl("POST", f"/api_v2/gpt/project/{self.project_id}/intent", data)

    def get_intent(self, intent_id):
        """GET intent detail."""
        return self._curl("GET", f"/api_v2/gpt/project/{self.project_id}/intent/{intent_id}")

    def update_intent(self, intent_id, data):
        """PUT intent — update an intent (full object)."""
        return self._curl("PUT", f"/api_v2/gpt/project/{self.project_id}/intent/{intent_id}", data)

    def toggle_intent(self, intent_id, enabled=True):
        """PUT intent status — enable or disable."""
        status = "ENABLED" if enabled else "DISABLED"
        return self._curl("PUT",
                          f"/api_v2/gpt/project/{self.project_id}/intent/{intent_id}/status",
                          {"status": status})

    def get_conversations_by_intent(self, intent, limit=50):
        """按意图名拉历史会话，每条带 USER 消息序列。

        实现：
          1. list_intents(category=None) 拿全量意图，按 name 找 intent_id
          2. POST /api_v2/gpt/project/{projectId}/transcripts/filter
             body: {"pageSize": limit, "pageIndex": 1, "intentId": <int>}
          3. 对每条 chatId 调 GET /api_v2/gpt/project/{projectId}/transcript/{chatId}
             取 role=USER 且 content 非空的消息

        返回：[{source_chat_id, intent, messages: [...], metadata: {...}}, ...]
        单条 chatId 拉取异常 → 跳过，不阻断整批。
        """
        intents_resp = self.list_intents(category=None)
        intents = intents_resp if isinstance(intents_resp, list) else \
            intents_resp.get("data", intents_resp.get("list", []))
        intent_id = None
        for it in intents:
            if isinstance(it, dict) and it.get("name") == intent:
                intent_id = it.get("id")
                break
        if intent_id is None:
            return []

        filter_resp = self._curl(
            "POST",
            f"/api_v2/gpt/project/{self.project_id}/transcripts/filter",
            {"pageSize": limit, "pageIndex": 1, "intentId": int(intent_id)},
        )
        rows = filter_resp.get("list", filter_resp) if isinstance(filter_resp, dict) else filter_resp
        if not isinstance(rows, list):
            return []

        out = []
        for row in rows:
            chat_id = row.get("chatId") or row.get("id")
            if not chat_id:
                continue
            try:
                detail = self.get_transcript(chat_id)
            except Exception:
                continue
            messages = []
            metadata = {}
            turns = detail.get("turns") if isinstance(detail, dict) else None
            if not turns and isinstance(detail, dict):
                turns = detail.get("messages", [])
            if isinstance(turns, list):
                for turn in turns:
                    if not isinstance(turn, dict):
                        continue
                    role = turn.get("role") or turn.get("type")
                    content = turn.get("content") or turn.get("message")
                    if role == "USER" and content:
                        messages.append(content)
                    if not metadata and isinstance(turn.get("metadata"), dict):
                        metadata = turn["metadata"]
            if not messages:
                continue
            out.append({
                "source_chat_id": chat_id,
                "intent": intent,
                "messages": messages,
                "metadata": metadata,
            })
        return out

    # ── Strategy ──

    def list_entities(self):
        """GET entities — get strategy condition metadata."""
        return self._curl("GET", f"/api_v2/gpt/project/{self.project_id}/entities")

    def list_strategies(self, page_size=100):
        """GET /api_v2/gpt/project/{projectId}/strategies?pageSize={N}&pageNum=1

        返回 {"list":[{id,name,intent,...}], "total":..., ...}
        sample_history_cases 间接通过策略发现"已配置回答"的意图集合。
        """
        return self._curl(
            "GET",
            f"/api_v2/gpt/project/{self.project_id}/strategies",
            query_params={"pageSize": page_size, "pageNum": 1},
        )

    def create_strategy(self, data):
        """POST strategy — create a strategy."""
        return self._curl("POST", f"/api_v2/gpt/project/{self.project_id}/strategy",
                          data, query_params={"v4": "true"})

    def update_strategy(self, strategy_id, data):
        """PUT strategy — update a strategy (full object)."""
        return self._curl("PUT",
                          f"/api_v2/gpt/project/{self.project_id}/strategy/{strategy_id}",
                          data, query_params={"v4": "true"})

    def toggle_strategy(self, strategy_id, enabled=True):
        """PUT strategy status — enable or disable."""
        status = "ENABLED" if enabled else "DISABLED"
        return self._curl("PUT",
                          f"/api_v2/gpt/project/{self.project_id}/strategy/{strategy_id}",
                          {"status": status}, query_params={"v4": "true"})

    # ── Templates ──

    def create_template(self, template):
        """POST template — create one reply template in the template library."""
        data = {
            "name": template.get("name", ""),
            "content": template.get("content", ""),
            "status": template.get("status", "ENABLED"),
            "multiContent": template.get("multiContent") or {"AUTO": template.get("content", "")},
        }
        if template.get("scene"):
            data["scene"] = template.get("scene")
        return self._curl(
            "POST",
            f"/api_v2/gpt/project/{self.project_id}/template",
            data,
            referer_path="/templateBase",
        )

    def update_template(self, template_id, name=None, content=None, status=None, multi_content=None):
        """PUT template — partial-update one reply template (only provided fields change).

        服务端 partial merge：只更新非 null 字段（name / content / status / multiContent）；
        传 content 时服务端自动同步 multiContent[AUTO]。改名撞已有模板名会报错。
        见 shulex-gpt TemplateController.updateTemplate。
        """
        data = {}
        if name is not None:
            data["name"] = name
        if content is not None:
            data["content"] = content
        if status is not None:
            data["status"] = status
        if multi_content is not None:
            data["multiContent"] = multi_content
        if not data:
            raise ValueError(
                "update-template needs at least one field to change: --name / --content / --status / multiContent"
            )
        return self._curl(
            "PUT",
            f"/api_v2/gpt/project/{self.project_id}/template/{template_id}",
            data,
            referer_path="/templateBase",
        )

    def list_templates(self, page_index=1, page_size=999, keyword="", scenes=None, status=None):
        """POST templates/filter — list reply templates."""
        data = {
            "pageIndex": page_index,
            "pagesize": page_size,
            "keyword": keyword,
        }
        if scenes:
            data["scenes"] = scenes
        if status:
            data["status"] = status
        return self._curl(
            "POST",
            f"/api_v2/gpt/project/{self.project_id}/templates/filter",
            data,
            referer_path="/templateBase",
        )

    def delete_templates(self, template_ids):
        """DELETE templates — batch delete reply templates by IDs."""
        return self._curl(
            "DELETE",
            f"/api_v2/gpt/project/{self.project_id}/templates",
            {"templateIds": [int(template_id) for template_id in template_ids]},
            referer_path="/templateBase",
        )

    # ── Knowledge ──

    def list_knowledge(
        self,
        page_index=1,
        page_size=50,
        keyword="",
        knowledge_type="ALL",
        directory_id=None,
    ):
        """POST getKnowledge — list knowledge items."""
        data = {
            "type": knowledge_type,
            "pageIndex": page_index,
            "pageSize": page_size,
            "keyword": keyword,
        }
        if directory_id is not None:
            data["directoryId"] = int(directory_id)
        return self._curl("POST", f"{self._qam_prefix}/project/{self.project_id}/getKnowledge", data,
                          referer_path="/knowledge")

    def get_knowledge(self, knowledge_id):
        """GET ku/{kuId} — read one QA/self-learning knowledge item."""
        return self._curl(
            "GET",
            f"{self._qam_prefix}/project/{self.project_id}/ku/{int(knowledge_id)}",
            referer_path="/knowledge",
        )

    def get_document(self, document_id):
        """GET document/{documentId} — read one FILE/WEBSITE document."""
        return self._curl(
            "GET",
            f"{self._qam_prefix}/project/{self.project_id}/document/{int(document_id)}",
            referer_path="/knowledge",
        )

    def get_product_knowledge(self, knowledge_id):
        """GET ku_product/{id} — read one product knowledge item."""
        return self._curl(
            "GET",
            f"{self._qam_prefix}/project/{self.project_id}/ku_product/{int(knowledge_id)}",
            referer_path="/knowledge",
        )

    def get_knowledge_by_type(self, knowledge_id, knowledge_type):
        """Read an exact item through the entity endpoint for its UI type."""
        normalized = str(knowledge_type).upper()
        if normalized in {"FILE", "WEBSITE"}:
            return self.get_document(knowledge_id)
        if normalized == "PRODUCT":
            return self.get_product_knowledge(knowledge_id)
        if normalized in {"QA", "LEARN_SELF"}:
            return self.get_knowledge(knowledge_id)
        raise ValueError("knowledge_type must be QA, LEARN_SELF, FILE, WEBSITE, or PRODUCT")

    def update_knowledge(self, knowledge_id, data):
        """PUT ku — update one knowledge item."""
        payload = dict(data)
        payload["kuId"] = int(knowledge_id)
        return self._curl(
            "PUT",
            f"{self._qam_prefix}/project/{self.project_id}/ku",
            payload,
            referer_path="/knowledge",
        )

    def update_kus(self, items):
        """PUT kus — batch update knowledge items (content, title, directoryId, etc.)."""
        if not isinstance(items, list) or not items:
            raise ValueError("items must be a non-empty array")
        formatted = []
        for item in items:
            row = dict(item)
            if "id" in row and "kuId" not in row:
                row["kuId"] = row.pop("id")
            if "kuId" not in row:
                raise ValueError("each item in batch update requires kuId or id")
            row["kuId"] = int(row["kuId"])
            formatted.append(row)
        return self._curl(
            "PUT",
            f"{self._qam_prefix}/project/{self.project_id}/kus",
            {"list": formatted},
            referer_path="/knowledge",
        )

    def update_document_content(self, document_id, data):
        """PUT document content for FILE/WEBSITE knowledge."""
        payload = dict(data)
        knowledge_type = str(payload.get("type", "")).upper()
        if knowledge_type not in {"FILE", "WEBSITE"}:
            raise ValueError("document type must be FILE or WEBSITE")
        payload["type"] = knowledge_type
        payload["knowledgeIds"] = [int(document_id)]
        # The backend reads metadata even when only the body changes.
        payload.setdefault("metadata", {})
        return self._curl(
            "PUT",
            f"{self._qam_prefix}/project/{self.project_id}/document/{int(document_id)}/contentV2",
            payload,
            referer_path="/knowledge",
        )

    def create_product_knowledge(self, data):
        """POST one PRODUCT knowledge item."""
        payload = dict(data)
        payload.setdefault("source", "MANUAL")
        payload.setdefault("published", True)
        payload.setdefault("isVisible", True)
        payload.setdefault("metadata", {"tags": []})
        return self._curl(
            "POST",
            f"{self._qam_prefix}/project/{self.project_id}/ku_product",
            payload,
            referer_path="/knowledge",
        )

    def update_product_knowledge(self, knowledge_id, data):
        """PUT one PRODUCT knowledge item using a complete merged payload."""
        payload = dict(data)
        payload["kuProductId"] = int(knowledge_id)
        return self._curl(
            "PUT",
            f"{self._qam_prefix}/project/{self.project_id}/ku_product",
            payload,
            referer_path="/knowledge",
        )

    def update_ku_products(self, items):
        """PUT ku_products — batch update product status (mainPush, enable/published)."""
        if not isinstance(items, list) or not items:
            raise ValueError("items must be a non-empty array")
        formatted = []
        for item in items:
            row = dict(item)
            if "kuProductId" in row and "id" not in row:
                row["id"] = row.pop("kuProductId")
            if "id" not in row:
                raise ValueError("each item in batch update requires id or kuProductId")
            entry = {"id": int(row["id"])}
            if "mainPush" in row:
                entry["mainPush"] = bool(row["mainPush"])
            if "enable" in row:
                entry["enable"] = bool(row["enable"])
            elif "published" in row:
                entry["enable"] = bool(row["published"])
            formatted.append(entry)
        return self._curl(
            "PUT",
            f"{self._qam_prefix}/project/{self.project_id}/ku_products",
            {"list": formatted},
            referer_path="/knowledge",
        )

    def operate_knowledge(self, request_list):
        """Delete, move, publish, unpublish, show, or hide mixed knowledge."""
        if not isinstance(request_list, list) or not request_list:
            raise ValueError("request_list must be a non-empty array")
        return self._curl(
            "POST",
            f"{self._qam_prefix}/project/{self.project_id}/updateKnowledge",
            {"requestList": request_list},
            referer_path="/knowledge",
        )

    def upload_qa(self, qa_list):
        """POST kus — upload QA knowledge. qa_list: [{title, content, ...}]."""
        items = []
        for qa in qa_list:
            items.append({
                "title": qa.get("title", ""),
                "content": qa.get("content", ""),
                "forceIndex": qa.get("forceIndex", True),
                "type": "QA",
                "published": qa.get("published", True),
                "taskType": qa.get("taskType", "MANUAL"),
                "metadata": qa.get("metadata", {"tags": []}),
                "directoryId": qa.get("directoryId", ""),
                "isVisible": qa.get("isVisible", True),
            })
        return self._curl("POST", f"{self._qam_prefix}/project/{self.project_id}/kus",
                          items, referer_path="/knowledge")

    def create_documents(self, documents, directory_id="", task_type="FILE",
                         task_url="MANUAL", published=True, is_visible=True):
        """Create source-document knowledge from uploaded files or URLs.

        ``documents`` contains API-level records with ``filePath``, ``docType``
        and ``fileType``.  Keeping this separate from QA creation is important:
        FILE/WEBSITE records are DOCUMENT knowledge, not KU/QA entries.
        """
        return self._curl("POST", f"{self._qam_prefix}/project/{self.project_id}/documents", {
            "documents": documents,
            "published": published,
            "taskType": task_type,
            "taskUrl": task_url,
            "isFullSiteCrawl": False,
            "metadata": {"tags": []},
            "directoryId": directory_id,
            "isVisible": is_visible,
        }, referer_path="/knowledge")

    def upload_web(self, urls, directory_id=""):
        """Create WEBSITE/DOCUMENT knowledge for URL sources."""
        docs = [{"filePath": url, "docType": "TC", "fileType": "website"} for url in urls]
        return self.create_documents(docs, directory_id=directory_id, task_type="WEB")

    # ── Isolation keywords ──
    def list_isolation_keywords(self, keyword="", page_index=1, page_size=50):
        """GET isolation keywords for the current project."""
        return self._curl(
            "GET",
            f"{self._qam_prefix}/project/{self.project_id}/isolation_keywords",
            query_params={
                "keyword": keyword,
                "pageIndex": page_index,
                "pageSize": page_size,
            },
            referer_path="/knowledge",
        )

    def list_all_isolation_keywords(self, keyword="", page_size=1000):
        """Fetch all isolation keywords by following pages until the last page."""
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        all_items = []
        page_index = 1
        while True:
            result = self.list_isolation_keywords(keyword, page_index, page_size)
            items = result.get("list", result) if isinstance(result, dict) else result
            if not isinstance(items, list):
                raise ValueError("isolation keyword list response must be an array")
            all_items.extend(items)
            if len(items) < page_size:
                return all_items
            page_index += 1

    def create_isolation_keyword(self, keyword):
        """POST one or more comma-separated isolation keywords."""
        return self._curl(
            "POST",
            f"{self._qam_prefix}/project/{self.project_id}/isolation_keyword",
            {"keyword": keyword},
            referer_path="/knowledge",
        )

    def update_isolation_keyword(self, keyword_id, keyword):
        """POST an updated isolation keyword value."""
        return self._curl(
            "POST",
            f"{self._qam_prefix}/project/{self.project_id}/isolation_keyword/{int(keyword_id)}",
            {"keyword": keyword},
            referer_path="/knowledge",
        )

    def delete_isolation_keyword(self, keyword_id):
        """DELETE an isolation keyword by ID."""
        return self._curl(
            "DELETE",
            f"{self._qam_prefix}/project/{self.project_id}/isolation_keyword/{int(keyword_id)}",
            referer_path="/knowledge",
        )

    def get_knowledge_isolation_keywords(self, knowledge_id, knowledge_type):
        """Read current isolation-keyword bindings for any knowledge UI type."""
        normalized = str(knowledge_type).upper()
        if normalized not in {"QA", "LEARN_SELF", "FILE", "WEBSITE", "PRODUCT"}:
            raise ValueError("knowledge_type must be QA, LEARN_SELF, FILE, WEBSITE, or PRODUCT")
        isolation_type = {
            "QA": "QA",
            "LEARN_SELF": "QA",
            "FILE": "DOCUMENT",
            "WEBSITE": "DOCUMENT",
            "PRODUCT": "PRODUCT",
        }[normalized]
        return self._curl(
            "GET",
            f"{self._qam_prefix}/project/{self.project_id}/knowledge/isolation_keywords",
            query_params={"knowledgeType": isolation_type, "knowledgeId": int(knowledge_id)},
            referer_path="/knowledge",
        )

    def batch_update_isolation_keyword_bindings(
        self, items=None, directory_ids=None, keyword_ids=None
    ):
        """Replace final isolation-keyword bindings for knowledge and directories.

        ``items`` contains knowledge-level bindings, while ``directory_ids``
        targets directory-level bindings. Callers must compute the complete final
        keyword set before invoking this raw backend operation.
        """
        items = [] if items is None else items
        directory_ids = [] if directory_ids is None else directory_ids
        keyword_ids = [] if keyword_ids is None else keyword_ids
        if not isinstance(items, list) or not isinstance(directory_ids, list) or not isinstance(keyword_ids, list):
            raise ValueError("items, directory_ids and keyword_ids must be arrays")
        if not items and not directory_ids and not keyword_ids:
            raise ValueError("isolation keyword binding update has no targets or keyword IDs")
        if items and directory_ids:
            raise ValueError("submit knowledge items and directory IDs in separate binding updates")

        for value in [*directory_ids, *keyword_ids]:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("directory_ids and keyword_ids must contain positive integer IDs")
        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("items must contain objects")
            knowledge_id = item.get("knowledgeId")
            item_keyword_ids = item.get("keywordIds")
            if isinstance(knowledge_id, bool) or not isinstance(knowledge_id, int) or knowledge_id <= 0:
                raise ValueError("items[].knowledgeId must be a positive integer")
            if not isinstance(item_keyword_ids, list):
                raise ValueError("items[].keywordIds must be an array")
            if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in item_keyword_ids):
                raise ValueError("items[].keywordIds must contain positive integer IDs")
            knowledge_type = str(item.get("knowledgeType", "QA")).upper()
            if knowledge_type not in {"QA", "LEARN_SELF", "FILE", "WEBSITE", "PRODUCT"}:
                raise ValueError("items[].knowledgeType must be QA, LEARN_SELF, FILE, WEBSITE, or PRODUCT")
            isolation_type = {
                "QA": "QA",
                "LEARN_SELF": "QA",
                "FILE": "DOCUMENT",
                "WEBSITE": "DOCUMENT",
                "PRODUCT": "PRODUCT",
            }[knowledge_type]
            normalized_items.append({
                "knowledgeType": isolation_type,
                "knowledgeId": knowledge_id,
                "keywordIds": list(dict.fromkeys(item_keyword_ids)),
            })

        return self._curl(
            "POST",
            f"{self._qam_prefix}/project/{self.project_id}/knowledge/isolation_keywords/batch",
            {
                "items": normalized_items,
                "directoryIds": list(dict.fromkeys(directory_ids)),
                "keywordIds": list(dict.fromkeys(keyword_ids)),
            },
            referer_path="/knowledge",
        )

    def list_directories(self):
        """GET directories — list the full KB directory tree (raw payload).

        Path prefix differs by env (mirrors front-end formatQamPath):
          prod    → /api_v2/qam/project/{p}/directories
          staging → /sns_v1/project/{p}/directories
        """
        return self._curl("GET", f"{self._qam_prefix}/project/{self.project_id}/directories",
                          query_params={"keyword": "", "kuPublished": ""},
                          referer_path="/knowledge")

    def edit_knowledge_tags(self, knowledge_ids, tag_list, knowledge_type="QA"):
        """Replace tags on the given knowledge items via the KB tag endpoint."""
        if not isinstance(knowledge_ids, list) or not knowledge_ids:
            raise ValueError("knowledge_ids must be a non-empty array")
        if not isinstance(tag_list, list):
            raise ValueError("tag_list must be an array")
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in knowledge_ids):
            raise ValueError("knowledge_ids must contain positive integer IDs")
        if any(not isinstance(value, str) or not value.strip() for value in tag_list):
            raise ValueError("tag_list must contain non-empty strings")
        return self._curl(
            "POST",
            f"{self._qam_prefix}/project/{self.project_id}/editTags",
            {
                "type": knowledge_type,
                "knowledgeIds": list(dict.fromkeys(knowledge_ids)),
                "tagList": list(dict.fromkeys(tag_list)),
            },
            referer_path="/knowledge",
        )

    def list_knowledge_tags(self, keyword=""):
        """GET project tag definitions used by knowledge metadata."""
        return self._curl(
            "GET",
            f"{self._qam_prefix}/project/{self.project_id}/searchKeywordAndIntents",
            query_params={"keyword": keyword},
            referer_path="/knowledge",
        )

    def create_folder(self, name, parent_id=0, folder_type="GENERIC"):
        """POST directory — create a knowledge folder."""
        return self._curl("POST", f"{self._qam_prefix}/project/{self.project_id}/directory", {
            "name": name, "parentId": parent_id, "type": folder_type,
        }, referer_path="/knowledge")

    def update_directory(self, directory_id, data):
        """PUT directory — rename or update one knowledge folder."""
        return self._curl(
            "PUT",
            f"{self._qam_prefix}/project/{self.project_id}/directory/{int(directory_id)}",
            dict(data),
            referer_path="/knowledge",
        )

    def move_directory(self, directory_id, parent_id):
        """GET directory/move — move one folder below another folder or root."""
        return self._curl(
            "GET",
            f"{self._qam_prefix}/project/{self.project_id}/directory/move",
            query_params={"currentId": int(directory_id), "parentId": int(parent_id)},
            referer_path="/knowledge",
        )

    def delete_directory(self, directory_id):
        """DELETE one directory recursively, including descendants and knowledge."""
        return self._curl(
            "DELETE",
            f"{self._qam_prefix}/project/{self.project_id}/directory/{int(directory_id)}",
            referer_path="/knowledge",
        )

    # ── Transcripts ──

    def list_transcripts(self, page_size=20, page_index=1, debug=False,
                         begin_ts=None, end_ts=None, touch_point=None,
                         bot_id=None, agent_id=None, intent_id=None,
                         handoff=None, keyword=None):
        """POST transcripts/filter — query inbox conversations."""
        data = {"pageSize": page_size, "pageIndex": page_index, "debug": debug}
        optional_fields = {
            "beginTimestamp": begin_ts,
            "endTimestamp": end_ts,
            "touchPoint": touch_point,
            "botId": int(bot_id) if bot_id is not None else None,
            "agentId": int(agent_id) if agent_id is not None else None,
            "intentId": int(intent_id) if intent_id is not None else None,
            "handoff": handoff,
            "keyword": keyword,
        }
        data.update({
            key: value
            for key, value in optional_fields.items()
            if value is not None
        })
        return self._curl("POST",
                          f"/api_v2/gpt/project/{self.project_id}/transcripts/filter", data)

    def resolve_transcript_chat_id(self, external_id, page_size=10, debug=False):
        """Resolve an inbox external conversation ID to an internal chatId.

        The Inbox page searches external IDs through transcripts/filter keyword.
        Reuse the same query here, then prefer an exact externId/externalId match.
        """
        result = self.list_transcripts(
            page_size=page_size,
            page_index=1,
            debug=debug,
            keyword=external_id,
        )
        rows = result.get("list", result) if isinstance(result, dict) else result
        if not isinstance(rows, list):
            rows = []

        target = str(external_id)
        exact = [
            row for row in rows
            if isinstance(row, dict)
            and str(row.get("externId") or row.get("externalId") or row.get("external_id") or "") == target
        ]
        candidates = exact or [row for row in rows if isinstance(row, dict)]
        if not candidates:
            return {"externalId": external_id, "chatId": None, "matches": []}

        def compact(row):
            return {
                "chatId": row.get("chatId") or row.get("id"),
                "externalId": row.get("externId") or row.get("externalId") or row.get("external_id"),
                "agentName": row.get("agentName", ""),
                "touchPoint": row.get("touchPoint", row.get("touchpoint", "")),
                "createdAt": row.get("createdAt", ""),
            }

        matches = [compact(row) for row in candidates]
        return {
            "externalId": external_id,
            "chatId": matches[0].get("chatId") if exact or len(matches) == 1 else None,
            "matchedBy": "exactExternalId" if exact else "keyword",
            "matches": matches,
        }

    def export_transcripts(self, page_size=20, page_index=1, debug=False,
                           begin_ts=None, end_ts=None, time_offset=8, **filters):
        """POST transcripts/export/async — submit async export task."""
        data = {"pageSize": page_size, "pageIndex": page_index,
                "debug": debug, "timeOffset": time_offset}
        if begin_ts:
            data["beginTimestamp"] = begin_ts
        if end_ts:
            data["endTimestamp"] = end_ts
        for key in ["handoff", "agentId", "strategyId", "intentId", "touchpoint"]:
            if key in filters and filters[key] is not None:
                data[key] = filters[key]
        return self._curl("POST",
                          f"/api_v2/gpt/project/{self.project_id}/transcripts/export/async", data)

    def get_export_tasks(self, page=1, page_size=10):
        """POST getLabelTask — poll export task status."""
        return self.get_label_tasks(page=page, page_size=page_size)

    # ── Batch testing / Download Center ──

    def get_sts_credentials(self):
        """Get temporary S3 credentials for GPT-side uploads such as batch tests."""
        return self._curl("GET", f"/api_v2/gpt/project/{self.project_id}/sts_credentials")

    def get_knowledge_sts_credentials(self):
        """Get the same knowledge-upload credentials used by anker-knowledge."""
        return self._curl("GET", f"{self._qam_prefix}/project/{self.project_id}/sts_credentials")

    def upload_temp_file(self, file_path, *, for_knowledge=False):
        """Upload one local file to the temporary S3 location and return its object key."""
        import boto3

        file_path = os.fspath(file_path)
        credentials = (self.get_knowledge_sts_credentials()
                       if for_knowledge else self.get_sts_credentials())
        required = ["accessKeyId", "secretAccessKey", "sessionToken", "region", "bucketName", "path"]
        missing = [key for key in required if not credentials.get(key)]
        if missing:
            raise RuntimeError(f"STS credentials missing fields: {', '.join(missing)}")

        key = f"{credentials['path']}{os.path.basename(file_path)}"
        session = boto3.session.Session(
            aws_access_key_id=credentials["accessKeyId"],
            aws_secret_access_key=credentials["secretAccessKey"],
            aws_session_token=credentials["sessionToken"],
            region_name=credentials["region"],
        )
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        session.client("s3").upload_file(
            file_path,
            credentials["bucketName"],
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return key

    def upload_batch_test_file(self, file_path):
        """Upload one generated .xlsx to the temporary S3 location and return its object key."""
        return self.upload_temp_file(file_path)

    def submit_batch_test(self, file_key, task_type, bot_id=None, metadata=None):
        """POST uploadMessage — create a REPLY or MULTI_TURN_REPLY Download Center task."""
        if task_type not in {"REPLY", "MULTI_TURN_REPLY"}:
            raise ValueError("task_type must be REPLY or MULTI_TURN_REPLY")
        payload = {"file": file_key, "type": task_type}
        if bot_id is not None:
            payload["botId"] = int(bot_id)
        if metadata:
            payload["metadata"] = metadata
        return self._curl(
            "POST",
            f"/api_v2/gpt/label/project/{self.project_id}/uploadMessage",
            payload,
        )

    def get_label_tasks(self, page=1, page_size=10, task_type=None):
        """POST getLabelTask — query Download Center tasks, optionally by task type."""
        payload = {"page": page, "pageSize": page_size}
        if task_type:
            payload["taskType"] = task_type
        return self._curl(
            "POST",
            f"/api_v2/gpt/label/project/{self.project_id}/getLabelTask",
            payload,
        )

    # ── label tree management ──

    def list_label_groups(self, tree_name=None):
        """GET getTreeInfo — list label groups."""
        params = {}
        if tree_name:
            params["treeName"] = tree_name
        return self._curl(
            "GET",
            f"/api_v2/gpt/label/project/{self.project_id}/getTreeInfo",
            query_params=params or None,
        )

    def create_label_group(self, tree_name, tree_describe="", condition=None, is_multi_tag=None):
        """POST updateTreeInfo CREATE — create one label group."""
        data = {"treeName": tree_name, "treeDescribe": tree_describe, "operateType": "CREATE"}
        if condition is not None:
            data["condition"] = condition
        if is_multi_tag is not None:
            data["isMultiTag"] = bool(is_multi_tag)
        return self._curl("POST", f"/api_v2/gpt/label/project/{self.project_id}/updateTreeInfo", data)

    def update_label_group(self, group_id, tree_name=None, tree_describe=None, condition=None, is_multi_tag=None):
        """POST updateTreeInfo UPDATE — update one label group."""
        data = {"id": int(group_id), "operateType": "UPDATE"}
        if tree_name is not None:
            data["treeName"] = tree_name
        if tree_describe is not None:
            data["treeDescribe"] = tree_describe
        if condition is not None:
            data["condition"] = condition
        if is_multi_tag is not None:
            data["isMultiTag"] = bool(is_multi_tag)
        return self._curl("POST", f"/api_v2/gpt/label/project/{self.project_id}/updateTreeInfo", data)

    def delete_label_group(self, group_id):
        """POST updateTreeInfo DELETE — delete one label group and its nodes."""
        return self._curl(
            "POST",
            f"/api_v2/gpt/label/project/{self.project_id}/updateTreeInfo",
            {"id": int(group_id), "operateType": "DELETE"},
        )

    def get_label_tree(self, tree_id, name=None):
        """GET getTagTree — return one label group's tree, optionally filtering by name/description."""
        params = {"treeId": int(tree_id)}
        if name:
            params["name"] = name
        return self._curl(
            "GET",
            f"/api_v2/gpt/label/project/{self.project_id}/getTagTree",
            query_params=params,
        )

    def get_label_detail_tree(self, tree_id, node_ids=None, node_names=None, parent_ids=None):
        """POST getDetailTree — query label node details."""
        data = {"treeId": int(tree_id)}
        if node_ids:
            data["nodeIds"] = [int(v) for v in node_ids]
        if node_names:
            data["nodeNames"] = list(node_names)
        if parent_ids:
            data["parentIds"] = [int(v) for v in parent_ids]
        return self._curl("POST", f"/api_v2/gpt/label/project/{self.project_id}/getDetailTree", data)

    def update_label_nodes(self, tree_id, nodes, operate_type):
        """POST updateNode — create/update/delete label nodes."""
        if operate_type not in {"CREATE", "UPDATE", "DELETE"}:
            raise ValueError("operate_type must be CREATE, UPDATE or DELETE")
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("nodes must be a non-empty list")
        data = {"treeId": int(tree_id), "operateType": operate_type, "nodes": nodes}
        return self._curl("POST", f"/api_v2/gpt/label/project/{self.project_id}/updateNode", data)

    def create_label_node(self, tree_id, node_name, describe, parent_id=0, example_list=None, is_tag=True):
        """Create one label node."""
        node = {
            "nodeName": node_name,
            "describe": describe,
            "parentId": int(parent_id or 0),
            "isTag": bool(is_tag),
            "exampleList": example_list or [],
        }
        return self.update_label_nodes(tree_id, [node], "CREATE")

    def update_label_node(self, tree_id, node_id, node_name=None, describe=None, parent_id=None,
                          example_list=None, is_tag=None):
        """Update one label node."""
        node = {"id": int(node_id)}
        if node_name is not None:
            node["nodeName"] = node_name
        if describe is not None:
            node["describe"] = describe
        if parent_id is not None:
            node["parentId"] = int(parent_id)
        if example_list is not None:
            node["exampleList"] = example_list
        if is_tag is not None:
            node["isTag"] = bool(is_tag)
        return self.update_label_nodes(tree_id, [node], "UPDATE")

    def delete_label_node(self, tree_id, node_id):
        """Delete one label node and its descendants."""
        return self.update_label_nodes(tree_id, [{"id": int(node_id)}], "DELETE")

    def download_label_template(self, template_type, target_path):
        """Download VOC_LABEL or VOC_LABEL_INIT template xlsx."""
        if template_type not in {"VOC_LABEL", "VOC_LABEL_INIT"}:
            raise ValueError("template_type must be VOC_LABEL or VOC_LABEL_INIT")
        return self._download(
            f"/api_v2/gpt/label/project/{self.project_id}/downloadLabelTemplate",
            target_path,
            query_params={"type": template_type},
        )

    def download_labels(self, tree_id, target_path):
        """Download current labels of one label group as xlsx."""
        return self._download(
            f"/api_v2/gpt/label/project/{self.project_id}/downloadLabel",
            target_path,
            query_params={"treeId": int(tree_id)},
        )

    def upload_labels(self, tree_id, file_key, upload_way=None):
        """POST uploadLabel — import an already uploaded xlsx S3 key into a label group."""
        data = {"treeId": int(tree_id), "file": file_key}
        if upload_way:
            data["uploadWay"] = upload_way
        return self._curl("POST", f"/api_v2/gpt/label/project/{self.project_id}/uploadLabel", data)

    def upload_label_file(self, tree_id, file_path, init=False):
        """Upload local xlsx to temp S3 and import it through uploadLabel."""
        file_key = self.upload_temp_file(file_path)
        return {
            "fileKey": file_key,
            "result": self.upload_labels(tree_id, file_key, upload_way="INIT" if init else None),
        }

    # ── Orders / Tracking ──

    def get_api_key(self):
        """GET accounts/apikey — get X-Token for external data APIs."""
        return self._curl("GET", "/api_v2/gpt/accounts/apikey")

    def query_order(self, order_id, source=None, api_key=None, base="https://desk.shulex.com"):
        """GET /standard/order — query order info (items, price, fulfillment, tracking)."""
        if not api_key:
            api_key = self.get_api_key()
        params = {"orderId": order_id}
        if source:
            params["source"] = source
        r = self._request_with_retry(
            "GET", f"{base}/api_v2/intelli/standard/order",
            params=params, headers={"X-Token": api_key},
        )
        return r.json() if r.text.strip() else {}

    def query_orders(self, order_id=None, email=None, source=None,
                     api_key=None, base="https://desk.shulex.com"):
        """GET /standard/orders — query orders by orderId or email."""
        if not api_key:
            api_key = self.get_api_key()
        params = {}
        if order_id:
            params["orderId"] = order_id
        if email:
            params["email"] = email
        if source:
            params["source"] = source
        r = self._request_with_retry(
            "GET", f"{base}/api_v2/intelli/standard/orders",
            params=params, headers={"X-Token": api_key},
        )
        return r.json() if r.text.strip() else {}

    def query_tracking(self, tracking_numbers, tracking_number=None, carriers=None,
                       api_key=None, base="https://desk.shulex.com"):
        """POST queryTrackingByPollingCarrier — query logistics tracking via 17Track."""
        if not api_key:
            api_key = self.get_api_key()
        if isinstance(tracking_numbers, str):
            tracking_numbers = [tracking_numbers]
        if not tracking_number and tracking_numbers:
            tracking_number = tracking_numbers[0]
        body = {"trackingNumbers": tracking_numbers, "trackingNumber": tracking_number}
        if carriers:
            body["carriers"] = carriers
        r = self._request_with_retry(
            "POST", f"{base}/api_v2/intelli/track17api/queryTrackingByPollingCarrier",
            headers={"X-Token": api_key}, json=body,
        )
        return r.json() if r.text.strip() else {}

    # ── Reports ──

    def _report_filter(self, begin_ts, end_ts, time_offset=8, bot_id=None,
                       touch_point=None, date_unit=None, **extra):
        f = {
            "beginTimestamp": begin_ts,
            "endTimestamp": end_ts,
            "projectId": int(self.project_id),
            "timeOffset": time_offset,
        }
        if bot_id is not None:
            f["botId"] = int(bot_id)
        if touch_point:
            f["touchPoint"] = touch_point
        if date_unit:
            f["dateUnit"] = date_unit
        f.update(extra)
        return f

    def report_transcript(self, begin_ts, end_ts, time_offset=8, bot_id=None,
                          touch_point=None, date_unit=None, **extra):
        """POST statement/transcript — ticket-level stats (resolution/escalation/AI reply rate).
        Requires CHILD_USER token — ACCOUNT_USER returns total=0 silently.
        """
        return self._curl("POST", "/api_v2/as_bot/statement/transcript",
                          self._report_filter(begin_ts, end_ts, time_offset, bot_id,
                                              touch_point, date_unit, **extra),
                          referer_path="/report")

    def report_message(self, begin_ts, end_ts, time_offset=8, bot_id=None,
                       touch_point=None, date_unit=None, **extra):
        """POST statement/message — message-level stats and trend."""
        return self._curl("POST", "/api_v2/as_bot/statement/message",
                          self._report_filter(begin_ts, end_ts, time_offset, bot_id,
                                              touch_point, date_unit, **extra),
                          referer_path="/report")

    def report_agent(self, begin_ts, end_ts, time_offset=8, bot_id=None,
                     touch_point=None, date_unit=None, agent_id=None, **extra):
        """POST statement/agent — agent-level ticket stats."""
        f = self._report_filter(begin_ts, end_ts, time_offset, bot_id, touch_point,
                                date_unit=date_unit, **extra)
        if agent_id is not None:
            f["agentId"] = int(agent_id)
        return self._curl("POST", "/api_v2/as_bot/statement/agent", f, referer_path="/report")

    def report_intent(self, begin_ts, end_ts, time_offset=8, bot_id=None,
                      touch_point=None, intent_id=None, date_unit=None, **extra):
        """POST statement/transcript/intent — intent-level ticket stats."""
        f = self._report_filter(begin_ts, end_ts, time_offset, bot_id,
                                touch_point, date_unit, **extra)
        if intent_id is not None:
            f["firstIntentId"] = int(intent_id)
        return self._curl("POST", "/api_v2/as_bot/statement/transcript/intent", f,
                          referer_path="/report")

    def report_satisfaction_summary(self, begin_ts, end_ts, time_offset=8,
                                    bot_id=None, touch_point=None, **extra):
        """POST statement/satisfaction/feedback — satisfaction summary (AI vs Human)."""
        return self._curl("POST", "/api_v2/as_bot/statement/satisfaction/feedback",
                          self._report_filter(begin_ts, end_ts, time_offset, bot_id, touch_point, **extra),
                          referer_path="/report")

    def report_satisfaction_list(self, begin_ts, end_ts, time_offset=8, page=1,
                                 page_size=20, bot_id=None, touch_point=None,
                                 assistant_role=None, satisfied=None, **extra):
        """POST statement/satisfaction/message — satisfaction detail list (paged).

        assistant_role: 'ASSISTANT' or 'HUMAN'
        satisfied: True (thumbs up) or False (thumbs down)
        Response key is 'satisfactions' (not 'records').
        """
        f = self._report_filter(begin_ts, end_ts, time_offset, bot_id, touch_point,
                                page=page, size=page_size, **extra)
        if assistant_role:
            f["assistantRole"] = assistant_role
        if satisfied is not None:
            f["satisfied"] = satisfied
        return self._curl("POST", "/api_v2/as_bot/statement/satisfaction/message", f,
                          referer_path="/report")

    def report_knowledge(self, begin_ts, end_ts, time_offset=8, page=1, page_size=20,
                         sort_by=None, bot_id=None, touch_point=None, source=None, **extra):
        """POST statement/knowledge — knowledge usage stats.

        sort_by: dict like {"TOTAL": "DESCEND"} or {"ESCALATION_RATE": "ASCEND"}
        """
        f = self._report_filter(begin_ts, end_ts, time_offset, bot_id, touch_point,
                                page=page, size=page_size, **extra)
        if sort_by:
            f["sortBy"] = sort_by
        if source:
            f["source"] = source
        return self._curl("POST", "/api_v2/as_bot/statement/knowledge", f, referer_path="/report")

    def report_escalation_reasons(self, begin_ts, end_ts, time_offset=8,
                                  date_unit="DAY", bot_id=None, touch_point=None, **extra):
        """POST statement/transcript/reason2 — escalation reason tree.

        date_unit: 'DAY' (main list) or 'WEEK' (last 4 weeks)
        """
        return self._curl("POST", "/api_v2/as_bot/statement/transcript/reason2",
                          self._report_filter(begin_ts, end_ts, time_offset, bot_id, touch_point,
                                              date_unit=date_unit, **extra),
                          referer_path="/report")

    def report_escalation_drilldown(self, begin_ts, end_ts, reason, time_offset=8,
                                    page=1, page_size=10, bot_id=None, touch_point=None, **extra):
        """POST statement/transcript/reason/three/level — escalation reason drilldown (paged)."""
        f = self._report_filter(begin_ts, end_ts, time_offset, bot_id, touch_point,
                                date_unit="DAY", **extra)
        f["reason"] = reason
        f["pageIndex"] = page
        f["pageSize"] = page_size
        return self._curl("POST", "/api_v2/as_bot/statement/transcript/reason/three/level", f,
                          referer_path="/report")

    def report_self_learning(self, begin_ts, end_ts, time_offset=8,
                             bot_id=None, touch_point=None, **extra):
        """POST statement/self-learning — self-learning topic stats and trend."""
        return self._curl("POST", "/api_v2/as_bot/statement/self-learning",
                          self._report_filter(begin_ts, end_ts, time_offset, bot_id, touch_point, **extra),
                          referer_path="/report")

    def report_livechat_summary(self, begin_ts, end_ts, time_offset=8, **extra):
        """POST livechat/report/summary — LiveChat pre-sales funnel and intent distribution."""
        return self._curl("POST", "/api_v2/as_bot/livechat/report/summary",
                          self._report_filter(begin_ts, end_ts, time_offset, **extra),
                          referer_path="/report")

    def report_livechat_table(self, begin_ts, end_ts, time_offset=8,
                              page=1, page_size=10, **extra):
        """POST livechat/report/table — LiveChat conversion detail table (paged)."""
        f = self._report_filter(begin_ts, end_ts, time_offset, **extra)
        f["page"] = {"page": page, "size": page_size}
        return self._curl("POST", "/api_v2/as_bot/livechat/report/table", f,
                          referer_path="/report")

    def report_inspection(self, start_date, end_date, dimension="ticket"):
        """POST inspection/ticket/count — AI inspection overview (ticket count, pass rate).

        start_date / end_date: 'YYYY-MM-DD' strings
        """
        return self._curl("POST", "/api_v2/intelli/inspection/ticket/count",
                          {"startTime": start_date, "endTime": end_date, "dimension": dimension},
                          referer_path="/report")

    def report_inspection_history(self, start_date, end_date, dimension="ticket"):
        """POST inspection/ticket/history — AI inspection issue history trend."""
        return self._curl("POST", "/api_v2/intelli/inspection/ticket/history",
                          {"startTime": start_date, "endTime": end_date, "dimension": dimension},
                          referer_path="/report")

    def report_feedback(self, begin_ts, end_ts, time_offset=8,
                        bot_id=None, touch_point=None, **extra):
        """POST statement/feedback — star rating distribution (1-10) with handoff breakdown."""
        return self._curl("POST", "/api_v2/as_bot/statement/feedback",
                          self._report_filter(begin_ts, end_ts, time_offset, bot_id, touch_point, **extra),
                          referer_path="/report")

    def report_agent_weekly_graph(self, begin_ts, end_ts, time_offset=8, **extra):
        """POST statement/graph/agent — agent weekly chart data."""
        return self._curl("POST", "/api_v2/as_bot/statement/graph/agent",
                          self._report_filter(begin_ts, end_ts, time_offset, **extra),
                          referer_path="/report")

    # ── Voice ──

    def list_voice_agents(self):
        """POST queryAgent with category=voice — list voice agents."""
        return self._curl("POST", "/api_v2/gpt/ap/queryAgent", {
            "projectId": int(self.project_id),
            "needRelation": True,
            "noMeta": True,
            "category": "voice",
        })

    def list_voice_transcripts(self, page_num=1, page_size=20, begin_ts=None, end_ts=None):
        """POST voice-report/transcript-page — list voice call transcript pages."""
        if begin_ts is None:
            begin_ts = int((time.time() - 30 * 86400) * 1000)
        if end_ts is None:
            end_ts = int((time.time() + 2 * 86400) * 1000)
        return self._curl_internal("POST", "/api_v2/as_bot/voice-report/transcript-page", {
            "pageNum": page_num, "pageSize": page_size,
            "beginTimestamp": begin_ts, "endTimestamp": end_ts,
        })

    def get_voice_transcript(self, history_id):
        """GET voice/transcript — get voice call transcript detail."""
        return self._curl_internal(
            "GET",
            f"/api_v2/gpt/voice/transcript/projectId/{self.project_id}/history/{history_id}")
