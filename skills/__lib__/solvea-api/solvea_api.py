#!/usr/bin/env python3
"""
Solvea API Client - Manage Solvea customer service agents via Solvea bot backend.

Usage:
    python3 solvea_api.py <command> [options]

Commands:
    get-project        Get projectId and botId from token
    replace-mock-data  Replace mock data by type (fully replaces old data for the same tenant and type)
    query-mock-data    Query mock data by type (--name required)
    list-agents        List all agents
    get-agent          Get agent detail by ID
    get-chatflow-graph Get latest chatFlowGraph for a CHAT_FLOW agent (--agent-id required)
    create-agent       Create a new agent
    update-agent       Update an existing agent (requires full object)
    update-chatflow    Save or publish an existing CHAT_FLOW graph (--agent-id required)
    list-plugins       List available tools
    get-plugin         Get tool detail by ID
    create-plugin      Create a new tool
    update-plugin      Update a tool (requires full object)
    delete-plugin      Delete a tool
    run-plugin         Test-run an HTTP tool without saving
    list-ai-fields     List fields exposed by the CHAT_FLOW canvas
    list-agent-ai-fields List fields accepted by Agent range validation
    get-ai-field-guide Get Tars AI Field initialization state
    initialize-ai-fields Initialize Tars system AI Fields
    list-managed-ai-fields Page Tars AI Field definitions
    get-managed-ai-field Get one Tars AI Field definition
    create-managed-ai-field Create one Tars custom AI Field
    update-managed-ai-field Update one Tars AI Field
    delete-managed-ai-field Delete one unused Tars custom AI Field
    toggle-managed-ai-field Enable or disable one Tars AI Field
    get-quality-status Get project AI quality inspection status
    set-quality-status Enable or disable project AI quality inspection
    list-quality-rules List quality inspection rules
    get-quality-rule Get one system quality inspection rule
    update-quality-rule Update one system quality inspection rule
    create-custom-quality-rule Create one custom quality inspection rule
    get-custom-quality-rule Get one custom quality inspection rule
    update-custom-quality-rule Update one custom quality inspection rule
    delete-custom-quality-rule Delete one custom quality inspection rule
    list-quality-alert-rules List quality inspection alert rules
    get-quality-alert-rule Get one quality inspection alert rule
    create-quality-alert-rule Create one quality inspection alert rule
    update-quality-alert-rule Update one quality inspection alert rule
    delete-quality-alert-rule Delete one quality inspection alert rule
    list-quality-alert-messages Page quality inspection alert messages
    get-quality-alert-message Get one quality inspection alert message
    chat               Send a chat message (single or multi-turn)
    chat-stream        Send a chat message via SSE stream and return aggregated final event
    chat-async         Submit an async chat message, returns AsyncReceipt
    get-async-result   Poll async chat result by receipt
    list-intents       List intents
    get-conversations-by-intent  Fetch historical USER conversations filtered by intent name
    create-intent      Create a new intent
    get-intent         Get intent detail
    update-intent      Update an intent
    toggle-intent      Enable/disable an intent
    list-entities      List strategy condition entities
    create-strategy    Create a new strategy
    update-strategy    Update a strategy
    toggle-strategy    Enable/disable a strategy
    list-strategies    List strategies (paged)
    list-templates     List reply templates
    create-template    Create one reply template
    update-template    Update one reply template (partial; --id + changed fields)
    delete-templates   Delete reply templates by IDs
    list-knowledge     List knowledge items
    get-knowledge      Get one knowledge item by ID
    get-knowledge-isolation-keywords Get isolation keywords bound to one knowledge item
    update-knowledge   Update one knowledge item
    batch-update-knowledge Batch update knowledge items (content, title, directoryId, etc.)
    update-document-content Update FILE/WEBSITE body content
    create-product-knowledge Create one product knowledge item
    update-product-knowledge Update one product knowledge item
    batch-update-products Batch update product status (mainPush, enable/published)
    operate-knowledge  Delete, move, publish, unpublish, show, or hide knowledge
    edit-knowledge-tags Add, replace, or remove tags on knowledge items
    list-knowledge-tags List configured knowledge tags
    upload-qa          Upload QA knowledge
    upload-web         Upload web knowledge
    list-directories   List the KB directory tree (slim by default; --raw for full)
    create-folder      Create a knowledge folder
    update-directory   Rename a knowledge folder
    move-directory     Move a knowledge folder
    delete-directory   Recursively delete a knowledge folder
    list-isolation-keywords List isolation keywords (paged)
    create-isolation-keyword Create one or more comma-separated isolation keywords
    update-isolation-keyword Update one isolation keyword
    delete-isolation-keyword Delete one isolation keyword
    batch-update-isolation-keyword-bindings Bind or revise keyword bindings for knowledge/directories
    list-transcripts   Filter inbox conversation records
    get-transcript     Get one conversation record by chatId
    resolve-transcript-chat-id Resolve an external inbox conversation ID to chatId
    get-chat-context   Compare one turn's saved context with current resources
    export-transcripts Submit async transcript export task
    get-export-tasks   Poll export task status
    upload-batch-test-file Upload a generated xlsx through temporary S3 credentials
    submit-batch-test  Create a Download Center REPLY or MULTI_TURN_REPLY test task
    get-batch-test-tasks Query batch-test progress in Download Center
    list-label-groups  List label groups
    create-label-group Create one label group
    update-label-group Update one label group
    delete-label-group Delete one label group
    get-label-tree     Query one label tree
    get-label-detail-tree Query label node details
    create-label-node  Create one label node
    update-label-node  Update one label node
    delete-label-node  Delete one label node
    download-label-template Download label import template
    download-labels    Download current labels of one group
    upload-labels      Upload local xlsx and import labels
    report-transcript  Ticket-level stats (resolution/escalation rate)
    report-message     Message-level stats and trend
    report-agent       Agent performance stats
    report-intent      Intent-level ticket stats
    report-satisfaction Satisfaction summary (AI vs Human)
    report-satisfaction-list Satisfaction detail list (paged)
    report-knowledge   Knowledge usage stats
    report-escalation  Escalation reason tree
    report-livechat    LiveChat pre-sales funnel summary
    report-livechat-table LiveChat conversion detail table
    report-inspection  AI inspection overview metrics
    report-self-learning Self-learning topic stats
    chat-report-*      Modern /chatReport page metrics (default Agent Analytics source)
    list-voice-agents  List voice agents
    list-voice-transcripts List voice call transcript pages
    get-voice-transcript   Get voice call transcript detail

Environment:
    SOLVEA_TOKEN       JWT token for staging (_token_staging cookie)
    SOLVEA_BASE_URL    Base URL (default: https://apps-staging.voc.ai)
    SOLVEA_PROJECT_ID  Project ID (default: auto-detect or 950)
    SOLVEA_PROD_TOKEN  JWT token for production (_token cookie)
    SOLVEA_PROD_URL    Production URL (default: https://apps.voc.ai)
"""

import json
import os
import sys
import argparse

from client import SolveaClient


def summarize_knowledge_result(result, include_tags=False):
    items = result.get("list", result) if isinstance(result, dict) else result
    if not isinstance(items, list):
        return result

    compact = []
    for k in items:
        item = {
            "id": k.get("knowledgeId"),
            "directoryId": k.get("directoryId"),
            "type": k.get("type", ""),
            "status": k.get("knowledgeStatus", k.get("status", "")),
            "isolationKeywords": k.get("isolationKeywords", []),
        }
        # getKnowledge returns one unified DTO, but each UI type populates a
        # different subset. Preserve the useful fields instead of forcing
        # FILE/WEBSITE/PRODUCT into the QA question/answer shape.
        for field in (
            "question", "answer", "name", "title", "url", "brief", "storageSize",
            "productTitle", "productId", "sku", "spuUrl", "describe",
        ):
            if k.get(field) is not None:
                item[field] = k[field]
        if include_tags:
            item["tags"] = k.get("tags", [])
        compact.append(item)
    if isinstance(result, dict):
        return {
            "total": result.get("total", result.get("totalCount", len(compact))),
            "list": compact,
        }
    return compact


def main():
    parser = argparse.ArgumentParser(
        description="Solvea API Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("command", help="API command to execute")
    parser.add_argument("--id", help="Resource ID (agent/intent/strategy/etc)")
    parser.add_argument("--ids", nargs="+", type=int, help="Resource IDs for batch commands")
    parser.add_argument("--data", help="JSON data string")
    parser.add_argument("--data-file", help="JSON data file path")
    parser.add_argument("--message", "-m", help="Chat message")
    parser.add_argument("--chat-id", help="Chat ID for multi-turn")
    parser.add_argument("--external-id", help="External inbox conversation ID, e.g. ZENDESK-store-123")
    parser.add_argument("--bot-id", help="Bot ID for chat")
    parser.add_argument("--category", default=None, help="Category filter")
    parser.add_argument("--name", help="Resource name; MockData commands use it as mock_type")
    parser.add_argument("--content", help="Content for create-template")
    parser.add_argument("--page", type=int, default=1, help="Page index")
    parser.add_argument("--page-size", type=int, default=50, help="Page size")
    parser.add_argument("--keyword", default="", help="Search keyword")
    parser.add_argument("--status", default=None, help="Status filter/value for reply templates, e.g. ENABLED")
    parser.add_argument("--scene", action="append", default=None,
                        help="Reply template scene filter/value. Can be repeated for list-templates.")
    parser.add_argument("--enable", action="store_true", help="Enable resource")
    parser.add_argument("--disable", action="store_true", help="Disable resource")
    parser.add_argument("--touch-point", default=None, help="Touch point filter")
    parser.add_argument("--urls", nargs="+", help="URLs for web knowledge")
    parser.add_argument("--parent-id", type=int, default=None, help="Parent folder ID")
    parser.add_argument("--max-depth", type=int, default=3,
                        help="Maximum directory depth for create/move operations (default: 3)")
    parser.add_argument("--tree-id", type=int, help="label group/tree ID")
    parser.add_argument("--node-ids", nargs="+", type=int, help="label node IDs")
    parser.add_argument("--node-names", nargs="+", help="label node names")
    parser.add_argument("--parent-ids", nargs="+", type=int, help="label parent node IDs")
    parser.add_argument("--template-type", choices=["init", "update"],
                        default="update", help="label template type")
    parser.add_argument("--output", help="Output file path for download commands")
    parser.add_argument("--init", action="store_true",
                        help="Import labels with uploadWay=INIT for an empty label group")
    parser.add_argument("--debug", action="store_true", help="Include debug data")
    parser.add_argument("--time-offset", type=int, default=8, help="Timezone offset in hours")
    parser.add_argument("--begin-ts", type=int, help="Begin timestamp (ms)")
    parser.add_argument("--end-ts", type=int, help="End timestamp (ms)")
    parser.add_argument("--handoff", choices=["true", "false"], default=None,
                        help="Transcript handoff filter: true or false")
    parser.add_argument("--agent-id", type=int, help="Agent ID")
    parser.add_argument("--intent-id", type=int, help="Intent ID for report-intent detail")
    parser.add_argument("--date-unit", default=None, help="Report date unit: DAY / WEEK / TOTAL")
    parser.add_argument("--sort-by", default=None, help="Report sort field JSON, e.g. '{\"TOTAL\":\"DESCEND\"}'")
    parser.add_argument("--assistant-role", default=None, help="Satisfaction role: ASSISTANT or HUMAN")
    parser.add_argument("--satisfied", default=None, choices=["true", "false"],
                        help="Satisfaction filter: true or false")
    parser.add_argument("--start-date", default=None, help="Start date YYYY-MM-DD (inspection reports)")
    parser.add_argument("--end-date", default=None, help="End date YYYY-MM-DD (inspection reports)")
    parser.add_argument("--channel", default=None, help="Agent Dashboard channel filter")
    parser.add_argument("--business-type", default=None, help="Agent Dashboard businessType filter")
    parser.add_argument("--granularity", choices=["day", "week"], default=None,
                        help="Agent Dashboard trend granularity")
    parser.add_argument("--week-start-date", default=None, help="Dashboard handoff week YYYY-MM-DD")
    parser.add_argument("--primary-reason", default=None, help="Dashboard handoff primary reason")
    parser.add_argument("--secondary-reason", default=None, help="Dashboard handoff secondary reason")
    parser.add_argument("--dimension", default="ticket", help="Inspection dimension (default: ticket)")
    parser.add_argument("--source", default=None, help="Knowledge source filter")
    parser.add_argument("--project-id", help="Project ID (overrides env var and auto-detection)")
    parser.add_argument("--directory-id", type=int, default=None,
                        help="Knowledge directory ID filter (list-knowledge)")
    parser.add_argument("--include-tags", action="store_true",
                        help="Opt in to include knowledge tags in list-knowledge summary; not sent to the API")
    parser.add_argument("--type", dest="knowledge_type", default="ALL",
                        help="Knowledge type filter: ALL / QA / FILE / WEBSITE / PRODUCT / LEARN_SELF")
    parser.add_argument("--raw", action="store_true",
                        help="Return raw API response for commands that normally summarize output")
    parser.add_argument("--all", action="store_true",
                        help="Fetch all pages where supported")
    parser.add_argument("--env", choices=["staging", "prod"],
                        default=os.environ.get("SOLVEA_ENV", "prod"),
                        help="Environment: prod (default) or staging")
    parser.add_argument("--history-id", help="Voice transcript history ID")
    parser.add_argument("--receipt", help="AsyncReceipt for get-async-result")
    parser.add_argument("--callback", help="Callback URL for chat-async")
    parser.add_argument("--file", help="Local xlsx path for upload-batch-test-file")
    parser.add_argument("--file-key", help="S3 object key returned by upload-batch-test-file")
    parser.add_argument("--task-type", choices=["REPLY", "MULTI_TURN_REPLY"],
                        help="Download Center batch-test task type")
    parser.add_argument("--expire-minutes", type=int,
                        help="Expire minutes for chat-async receipt")
    parser.add_argument("--intent", help="Intent name (get-conversations-by-intent)")
    parser.add_argument("--inspection-key", help="Quality inspection rule key")
    parser.add_argument("--limit", type=int, default=50,
                        help="Result limit (get-conversations-by-intent)")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    parser.add_argument("--publish", action="store_true",
                        help="Publish update-chatflow instead of saving a draft")
    parser.add_argument("--confirm-delete", action="store_true",
                        help="Required safety acknowledgement for destructive delete commands")
    args = parser.parse_args()

    client = SolveaClient(env=args.env, project_id=args.project_id)
    handoff = None if args.handoff is None else args.handoff == "true"

    def load_data():
        if args.data:
            return json.loads(args.data)
        if args.data_file:
            with open(args.data_file) as f:
                return json.load(f)
        return None

    def output(result):
        if args.pretty:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False))

    def update_chatflow():
        if not args.agent_id:
            raise ValueError("update-chatflow requires --agent-id")
        graph = load_data()
        if graph is None:
            raise ValueError("update-chatflow requires --data or --data-file")
        return client.update_chatflow(args.agent_id, graph, publish=args.publish)

    def replace_mock_data():
        if not args.name:
            raise ValueError("replace-mock-data requires --name")
        records = load_data()
        if not isinstance(records, list):
            raise ValueError("replace-mock-data requires --data or --data-file with a JSON array")
        return client.replace_mock_data(args.name, records)

    def query_mock_data():
        if not args.name:
            raise ValueError("query-mock-data requires --name")
        return client.query_mock_data(args.name)

    def run_plugin():
        data = load_data()
        if isinstance(data, dict) and "externalHttpCallConfig" in data:
            return client.run_http_plugin(
                data["externalHttpCallConfig"],
                data.get("externalHttpCallRequestBody"),
            )
        return client.run_http_plugin(data)

    def require_object_data(command):
        data = load_data()
        if not isinstance(data, dict):
            raise ValueError(f"{command} requires --data or --data-file with a JSON object")
        return data

    def set_quality_status():
        if args.enable == args.disable:
            raise ValueError("set-quality-status requires exactly one of --enable or --disable")
        return client.update_quality_inspection_status(args.enable)

    def require_inspection_key(command):
        if not args.inspection_key:
            raise ValueError(f"{command} requires --inspection-key")
        return args.inspection_key

    cmd = args.command.replace("-", "_")

    # ── Summary helpers: CLI output must stay under ~200 lines to avoid Bash tool truncation ──

    def summary_agents():
        agents = client.list_agents(category=args.category or "text")
        if isinstance(agents, list):
            return [{"id": a.get("id"), "name": a.get("name"), "type": a.get("type"),
                     "description": a.get("description", "")} for a in agents]
        return agents

    def summary_plugins():
        plugins = client.list_plugins()
        if isinstance(plugins, list):
            return [{"id": p.get("id"), "name": p.get("name"), "type": p.get("type"),
                     "description": p.get("description", ""), "visible": p.get("visible")}
                    for p in plugins]
        return plugins

    def summary_intents():
        result = client.list_intents(category=args.category or "E_COMMERCE")
        intents = result if isinstance(result, list) else result.get("data", result.get("list", []))
        if isinstance(intents, list):
            return [{"id": i.get("id"), "name": i.get("name"), "status": i.get("status"),
                     "description": i.get("example") or i.get("description", "")} for i in intents]
        return result

    def summary_knowledge():
        result = client.list_knowledge(
            page_index=args.page,
            page_size=args.page_size,
            keyword=args.keyword,
            knowledge_type=args.knowledge_type,
            directory_id=args.directory_id,
        )
        if args.raw:
            return result
        return summarize_knowledge_result(result, include_tags=args.include_tags)

    def summary_directories():
        # 默认精简：目录树每节点只留 id/name/kuCount/children + 顶层 totalKuCount；--raw 出完整结构
        result = client.list_directories()
        if args.raw:
            return result

        def slim(node):
            return {
                "id": node.get("id"),
                "name": node.get("name"),
                "kuCount": node.get("kuCount"),
                "children": [slim(c) for c in (node.get("children") or [])],
            }

        if isinstance(result, list):
            return [slim(n) for n in result]
        if isinstance(result, dict):
            key = next((k for k in ("list", "records", "data") if isinstance(result.get(k), list)), None)
            out = {}
            if result.get("totalKuCount") is not None:
                out["totalKuCount"] = result.get("totalKuCount")
            out["list"] = [slim(n) for n in result.get(key, [])] if key else []
            return out
        return result

    def summary_templates():
        result = client.list_templates(
            page_index=args.page,
            page_size=args.page_size,
            keyword=args.keyword,
            scenes=args.scene,
            status=[args.status] if args.status else None,
        )
        items = result.get("list", result) if isinstance(result, dict) else result
        if isinstance(items, list):
            compact = [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "content": item.get("content", ""),
                    "status": item.get("status", ""),
                    "scene": item.get("scene", ""),
                }
                for item in items
            ]
            if isinstance(result, dict):
                return {"total": result.get("total", result.get("totalCount", len(compact))), "list": compact}
            return compact
        return result

    def create_template():
        data = load_data() or {}
        if args.name:
            data["name"] = args.name
        if args.content:
            data["content"] = args.content
        if args.status:
            data["status"] = args.status
        if args.scene:
            data["scene"] = args.scene[0]
        if not data.get("name") or not data.get("content"):
            raise ValueError("create-template requires --name/--content or --data/--data-file with name and content")
        return client.create_template(data)

    def update_template():
        if not args.id:
            raise ValueError("update-template requires --id (templateId)")
        data = load_data() or {}
        # 只传要改的字段；multiContent 走 --data/--data-file（含多语种时）
        return client.update_template(
            args.id,
            name=args.name if args.name else data.get("name"),
            content=args.content if args.content else data.get("content"),
            status=args.status if args.status else data.get("status"),
            multi_content=data.get("multiContent"),
        )

    def delete_templates():
        if not args.confirm_delete:
            raise ValueError("delete-templates requires --confirm-delete after explicit user acknowledgement")
        data = load_data() or {}
        template_ids = args.ids or data.get("templateIds") or data.get("ids")
        if not template_ids:
            raise ValueError("delete-templates requires --ids or --data/--data-file with templateIds")
        return client.delete_templates(template_ids)

    def require_tree_id(command):
        if not args.tree_id:
            raise ValueError(f"{command} requires --tree-id")
        return args.tree_id

    def require_id(command):
        if not args.id:
            raise ValueError(f"{command} requires --id")
        return args.id

    def create_label_group():
        data = load_data() or {}
        tree_name = args.name or data.get("treeName")
        if not tree_name:
            raise ValueError("create-label-group requires --name or --data/--data-file with treeName")
        return client.create_label_group(
            tree_name,
            tree_describe=data.get("treeDescribe", ""),
            condition=data.get("condition"),
            is_multi_tag=data.get("isMultiTag"),
        )

    def update_label_group():
        data = load_data() or {}
        return client.update_label_group(
            require_id("update-label-group"),
            tree_name=args.name if args.name else data.get("treeName"),
            tree_describe=data.get("treeDescribe"),
            condition=data.get("condition"),
            is_multi_tag=data.get("isMultiTag"),
        )

    def get_label_tree():
        return client.get_label_tree(require_tree_id("get-label-tree"), name=args.name or args.keyword)

    def get_label_detail_tree():
        return client.get_label_detail_tree(
            require_tree_id("get-label-detail-tree"),
            node_ids=args.node_ids,
            node_names=args.node_names,
            parent_ids=args.parent_ids,
        )

    def create_label_node():
        data = load_data() or {}
        node_name = args.name or data.get("nodeName")
        describe = args.content if args.content is not None else data.get("describe", "")
        if not node_name:
            raise ValueError("create-label-node requires --name or --data/--data-file with nodeName")
        return client.create_label_node(
            require_tree_id("create-label-node"),
            node_name,
            describe,
            parent_id=data.get("parentId", args.parent_id),
            example_list=data.get("exampleList") or [],
            is_tag=data.get("isTag", True),
        )

    def update_label_node():
        data = load_data() or {}
        return client.update_label_node(
            require_tree_id("update-label-node"),
            require_id("update-label-node"),
            node_name=args.name if args.name else data.get("nodeName"),
            describe=args.content if args.content is not None else data.get("describe"),
            parent_id=data.get("parentId"),
            example_list=data.get("exampleList"),
            is_tag=data.get("isTag"),
        )

    def delete_label_node():
        tree_id = require_tree_id("delete-label-node")
        node_id = require_id("delete-label-node")
        return client.delete_label_node(
            tree_id,
            node_id,
        )

    def download_label_template():
        output_path = args.output or f"{args.template_type.lower()}_template.xlsx"
        template_type = "VOC_LABEL_INIT" if args.template_type == "init" else "VOC_LABEL"
        return {"file": client.download_label_template(template_type, output_path)}

    def download_labels():
        tree_id = require_tree_id("download-labels")
        output_path = args.output or f"labels_{tree_id}.xlsx"
        return {"file": client.download_labels(tree_id, output_path)}

    def upload_labels():
        tree_id = require_tree_id("upload-labels")
        if not args.file:
            raise ValueError("upload-labels requires --file")
        return client.upload_label_file(tree_id, args.file, init=args.init)

    def get_knowledge():
        if not args.id:
            raise ValueError("get-knowledge requires --id")
        if args.knowledge_type == "ALL":
            raise ValueError("get-knowledge requires --type QA, LEARN_SELF, FILE, WEBSITE, or PRODUCT")
        return client.get_knowledge_by_type(int(args.id), args.knowledge_type)

    def get_knowledge_isolation_keywords():
        if not args.id:
            raise ValueError("get-knowledge-isolation-keywords requires --id")
        if args.knowledge_type == "ALL":
            raise ValueError("get-knowledge-isolation-keywords requires an explicit --type")
        return client.get_knowledge_isolation_keywords(int(args.id), args.knowledge_type)

    def update_knowledge():
        if not args.id:
            raise ValueError("update-knowledge requires --id")
        data = load_data()
        if not isinstance(data, dict):
            raise ValueError("update-knowledge requires --data or --data-file with a JSON object")
        payload = dict(data)
        if "directoryId" not in payload:
            current = client.get_knowledge(int(args.id))
            if isinstance(current, dict) and current.get("directoryId") is not None:
                payload["directoryId"] = current["directoryId"]
        return client.update_knowledge(int(args.id), payload)

    def batch_update_knowledge():
        data = load_data()
        items = data.get("list") if isinstance(data, dict) and "list" in data else data
        if not isinstance(items, list) or not items:
            raise ValueError("batch-update-knowledge requires a JSON array or object with list")
        formatted = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Every item in batch-update-knowledge must be a JSON object")
            row = dict(item)
            if "id" in row and "kuId" not in row:
                row["kuId"] = row.pop("id")
            if "kuId" not in row:
                raise ValueError("Every item requires kuId or id")
            if "directoryId" not in row:
                current = client.get_knowledge(int(row["kuId"]))
                if isinstance(current, dict) and current.get("directoryId") is not None:
                    row["directoryId"] = current["directoryId"]
            formatted.append(row)
        return client.update_kus(formatted)

    def update_document_content():
        if not args.id:
            raise ValueError("update-document-content requires --id")
        knowledge_type = str(args.knowledge_type).upper()
        if knowledge_type not in {"FILE", "WEBSITE"}:
            raise ValueError("update-document-content requires --type FILE or WEBSITE")
        changes = require_object_data("update-document-content")
        unknown = set(changes) - {"fileText", "filePath", "title"}
        if unknown:
            raise ValueError(f"Unsupported document content fields: {', '.join(sorted(unknown))}")
        if changes.get("fileText") is None and changes.get("filePath") is None:
            raise ValueError("update-document-content requires fileText or filePath")

        current = client.get_document(int(args.id))
        if not isinstance(current, dict):
            raise ValueError(f"Could not read document {args.id} before update")
        payload = {
            "type": knowledge_type,
            "directoryId": current.get("directoryId"),
            "fileName": current.get("fileName") or current.get("name") or current.get("title"),
            "title": current.get("title") or current.get("fileName") or current.get("name"),
            "metadata": current.get("metadata") if isinstance(current.get("metadata"), dict) else {},
        }
        payload.update(changes)
        payload["type"] = knowledge_type
        return client.update_document_content(int(args.id), payload)

    def create_product_knowledge():
        data = require_object_data("create-product-knowledge")
        for field in ("title", "spuUrl"):
            if not data.get(field):
                raise ValueError(f"create-product-knowledge requires {field}")
        return client.create_product_knowledge(data)

    def update_product_knowledge():
        if not args.id:
            raise ValueError("update-product-knowledge requires --id")
        changes = require_object_data("update-product-knowledge")
        current = client.get_product_knowledge(int(args.id))
        if not isinstance(current, dict):
            raise ValueError(f"Could not read product knowledge {args.id} before update")
        allowed_fields = {
            "productId", "tags", "documentId", "title", "handle", "vendor",
            "category", "brand", "productStatus", "country", "spuUrl", "image",
            "platform", "currency", "price", "compareAtPrice", "describe", "source",
            "skuList", "directoryId", "published", "metadata", "specialTagMap",
            "isVisible", "optionName",
        }
        unknown = set(changes) - allowed_fields - {"kuProductId", "id"}
        if unknown:
            raise ValueError(f"Unsupported product fields: {', '.join(sorted(unknown))}")
        payload = {key: value for key, value in current.items() if key in allowed_fields}
        payload.update({key: value for key, value in changes.items() if key in allowed_fields})
        missing = [
            field for field in ("title", "describe", "spuUrl", "image", "source", "published", "isVisible")
            if payload.get(field) is None or payload.get(field) == ""
        ]
        if missing:
            raise ValueError(f"Product detail is incomplete: {', '.join(missing)}")
        return client.update_product_knowledge(int(args.id), payload)

    def batch_update_products():
        data = load_data()
        items = data.get("list") if isinstance(data, dict) and "list" in data else data
        if not isinstance(items, list) or not items:
            raise ValueError("batch-update-products requires a JSON array or object with list")
        formatted = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Every item in batch-update-products must be a JSON object")
            row = dict(item)
            if "kuProductId" in row and "id" not in row:
                row["id"] = row.pop("kuProductId")
            if "id" not in row:
                raise ValueError("Every item requires id or kuProductId")
            entry = {"id": int(row["id"])}
            if "mainPush" in row:
                entry["mainPush"] = bool(row["mainPush"])
            if "enable" in row:
                entry["enable"] = bool(row["enable"])
            elif "published" in row:
                entry["enable"] = bool(row["published"])
            formatted.append(entry)
        return client.update_ku_products(formatted)

    def directory_index():
        result = client.list_directories()
        if isinstance(result, list):
            roots = result
        elif isinstance(result, dict):
            roots = next(
                (result.get(key) for key in ("list", "records", "data") if isinstance(result.get(key), list)),
                [],
            )
        else:
            roots = []
        index = {}

        def walk(node, depth, parent_id):
            node_id = node.get("id")
            if node_id is None:
                return
            index[int(node_id)] = {"node": node, "depth": depth, "parentId": parent_id}
            for child in node.get("children") or []:
                walk(child, depth + 1, int(node_id))

        for root in roots:
            walk(root, 1, 0)
        return index

    def subtree_ids(index, directory_id):
        descendants = {directory_id}
        changed = True
        while changed:
            changed = False
            for node_id, item in index.items():
                if item["parentId"] in descendants and node_id not in descendants:
                    descendants.add(node_id)
                    changed = True
        return descendants

    def create_folder():
        if not args.name:
            raise ValueError("create-folder requires --name")
        if args.max_depth <= 0:
            raise ValueError("--max-depth must be positive")
        parent_id = args.parent_id if args.parent_id is not None else 0
        if parent_id:
            index = directory_index()
            if parent_id not in index:
                raise ValueError(f"Parent directory {parent_id} was not found")
            if index[parent_id]["depth"] + 1 > args.max_depth:
                raise ValueError(f"Directory would exceed maximum depth {args.max_depth}")
        return client.create_folder(args.name, parent_id=parent_id)

    def update_directory():
        if not args.id:
            raise ValueError("update-directory requires --id")
        data = load_data() or {}
        if not isinstance(data, dict):
            raise ValueError("update-directory requires a JSON object")
        if args.name:
            data["name"] = args.name
        if not data.get("name"):
            raise ValueError("update-directory requires --name or data.name")
        index = directory_index()
        if int(args.id) not in index:
            raise ValueError(f"Directory {args.id} was not found")
        return client.update_directory(int(args.id), {"name": data["name"]})

    def move_directory():
        if not args.id:
            raise ValueError("move-directory requires --id")
        if args.parent_id is None:
            raise ValueError("move-directory requires --parent-id; use 0 for root")
        if args.max_depth <= 0:
            raise ValueError("--max-depth must be positive")
        directory_id = int(args.id)
        parent_id = int(args.parent_id)
        index = directory_index()
        if directory_id not in index:
            raise ValueError(f"Directory {directory_id} was not found")
        if parent_id and parent_id not in index:
            raise ValueError(f"Parent directory {parent_id} was not found")
        descendants = subtree_ids(index, directory_id)
        if parent_id in descendants:
            raise ValueError("A directory cannot be moved into itself or its descendants")
        current_depth = index[directory_id]["depth"]
        subtree_height = max(index[node_id]["depth"] - current_depth + 1 for node_id in descendants)
        parent_depth = index[parent_id]["depth"] if parent_id else 0
        if parent_depth + subtree_height > args.max_depth:
            raise ValueError(f"Moved subtree would exceed maximum depth {args.max_depth}")
        return client.move_directory(directory_id, parent_id)

    def delete_directory():
        if not args.id:
            raise ValueError("delete-directory requires --id")
        if not args.confirm_delete:
            raise ValueError("delete-directory requires --confirm-delete after explicit user acknowledgement")
        index = directory_index()
        if int(args.id) not in index:
            raise ValueError(f"Directory {args.id} was not found")
        return client.delete_directory(int(args.id))

    def operate_knowledge():
        data = load_data()
        request_list = data.get("requestList") if isinstance(data, dict) else data
        if not isinstance(request_list, list) or not request_list:
            raise ValueError("operate-knowledge requires a JSON array or object with requestList")
        supported_types = {"QA", "LEARN_SELF", "FILE", "WEBSITE", "PRODUCT"}
        supported_operations = {"DELETE", "MOVE", "PUBLISH", "UNPUBLISH", "VISIBLE", "INVISIBLE"}
        normalized = []
        move_directory_ids = set()
        for item in request_list:
            if not isinstance(item, dict):
                raise ValueError("Every knowledge operation must be an object")
            knowledge_type = str(item.get("knowledgeType", "")).upper()
            operation = str(item.get("operateType", "")).upper()
            if knowledge_type not in supported_types:
                raise ValueError(f"Unsupported knowledge type: {knowledge_type}")
            if operation not in supported_operations:
                raise ValueError(f"Unsupported knowledge operation: {operation}")
            try:
                knowledge_id = int(item["knowledgeId"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("Every knowledge operation requires a numeric knowledgeId") from None
            normalized_item = {
                "knowledgeType": knowledge_type,
                "knowledgeId": knowledge_id,
                "operateType": operation,
            }
            if operation == "MOVE":
                try:
                    normalized_item["directoryId"] = int(item["directoryId"])
                except (KeyError, TypeError, ValueError):
                    raise ValueError("MOVE requires a numeric directoryId") from None
                move_directory_ids.add(normalized_item["directoryId"])
            client.get_knowledge_by_type(knowledge_id, knowledge_type)
            normalized.append(normalized_item)
        if any(item["operateType"] == "DELETE" for item in normalized) and not args.confirm_delete:
            raise ValueError("DELETE requires --confirm-delete after explicit user acknowledgement")
        if move_directory_ids:
            index = directory_index()
            missing_directories = sorted(directory_id for directory_id in move_directory_ids if directory_id not in index)
            if missing_directories:
                raise ValueError(f"Target directories were not found: {missing_directories}")
        return client.operate_knowledge(normalized)

    def edit_knowledge_tags():
        data = require_object_data("edit-knowledge-tags")
        knowledge_ids = data.get("knowledgeIds")
        requested_tags = data.get("tagList")
        if not isinstance(knowledge_ids, list) or not knowledge_ids:
            raise ValueError("edit-knowledge-tags requires non-empty knowledgeIds")
        if not isinstance(requested_tags, list):
            raise ValueError("edit-knowledge-tags requires tagList array")
        operation = data.get("operation", "append")
        if operation not in {"append", "replace", "remove"}:
            raise ValueError("edit-knowledge-tags operation must be append, replace, or remove")

        knowledge_type = str(data.get("type", "QA")).upper()
        updates = []
        for knowledge_id in knowledge_ids:
            knowledge = client.get_knowledge_by_type(int(knowledge_id), knowledge_type)
            if not knowledge:
                raise ValueError(f"Could not read knowledge {knowledge_id} before tag update")
            current = knowledge.get("tags")
            if not isinstance(current, list):
                current = (knowledge.get("metadata") or {}).get("tags", [])
            if not isinstance(current, list):
                current = []
            if operation == "append":
                target = list(dict.fromkeys([*current, *requested_tags]))
            elif operation == "remove":
                target = [tag for tag in current if tag not in requested_tags]
            else:
                target = list(dict.fromkeys(requested_tags))
            updates.append(client.edit_knowledge_tags(
                knowledge_ids=[int(knowledge_id)],
                tag_list=target,
                knowledge_type=knowledge_type,
            ))
        return {"success": True, "results": updates}

    def summary_knowledge_tags():
        result = client.list_knowledge_tags(keyword=args.keyword)
        if args.raw:
            return result
        if isinstance(result, dict) and isinstance(result.get("metadataTagAll"), list):
            return {"tags": result["metadataTagAll"]}
        return result

    def summary_isolation_keywords():
        if args.all:
            return client.list_all_isolation_keywords(keyword=args.keyword, page_size=args.page_size)
        result = client.list_isolation_keywords(
            keyword=args.keyword,
            page_index=args.page,
            page_size=args.page_size,
        )
        if args.raw:
            return result
        items = result.get("list", result) if isinstance(result, dict) else result
        if not isinstance(items, list):
            return result
        compact = [
            {
                "id": item.get("id"),
                "keyword": item.get("keyword", ""),
                "bindCount": item.get("bindCount", 0),
                "projectId": item.get("projectId"),
                "tenantId": item.get("tenantId"),
                "createdAt": item.get("createdAt"),
                "updatedAt": item.get("updatedAt"),
            }
            for item in items
        ]
        return compact

    def create_isolation_keyword():
        if not args.keyword:
            raise ValueError("create-isolation-keyword requires --keyword")
        requested = list(dict.fromkeys(part.strip() for part in args.keyword.split(",") if part.strip()))
        if not requested:
            raise ValueError("create-isolation-keyword requires at least one non-empty keyword")
        existing = client.list_all_isolation_keywords(page_size=args.page_size)
        existing_names = {str(item.get("keyword", "")).strip() for item in existing}
        duplicates = [name for name in requested if name in existing_names]
        pending = [name for name in requested if name not in existing_names]
        if not pending:
            return {"duplicate": duplicates, "failed": [], "success": [], "created": False}
        result = client.create_isolation_keyword(",".join(pending))
        if isinstance(result, dict):
            result = dict(result)
            result["duplicate"] = duplicates + list(result.get("duplicate", []))
            result["created"] = True
        return result

    def update_isolation_keyword():
        if not args.id:
            raise ValueError("update-isolation-keyword requires --id")
        if not args.keyword:
            raise ValueError("update-isolation-keyword requires --keyword")
        return client.update_isolation_keyword(int(args.id), args.keyword)

    def delete_isolation_keyword():
        if not args.id:
            raise ValueError("delete-isolation-keyword requires --id")
        if not args.confirm_delete:
            raise ValueError("delete-isolation-keyword requires --confirm-delete after explicit user acknowledgement")
        return client.delete_isolation_keyword(int(args.id))

    def batch_update_isolation_keyword_bindings():
        data = require_object_data("batch-update-isolation-keyword-bindings")
        operation = str(data.get("operation", "append")).lower()
        if operation not in {"append", "remove", "replace"}:
            raise ValueError("operation must be append, remove, or replace")

        items = data.get("items") or []
        directory_ids = data.get("directoryIds") or []
        if not items and not directory_ids:
            raise ValueError("binding update requires knowledge items or directory IDs")
        if directory_ids and operation != "replace":
            raise ValueError(
                "directory bindings require operation=replace because the backend replaces the final binding set"
            )
        if directory_ids and data.get("confirmReplace") is not True:
            raise ValueError(
                "directory binding replacement requires confirmReplace=true after explicit user confirmation"
            )

        resolved_items = []
        for item in items:
            knowledge_id = item.get("knowledgeId") if isinstance(item, dict) else None
            knowledge_type = (item.get("knowledgeType") if isinstance(item, dict) else None)
            knowledge_type = knowledge_type.upper() if isinstance(knowledge_type, str) else None
            if knowledge_id is None:
                raise ValueError("Could not read existing binding for every knowledge item")
            if knowledge_type is None:
                raise ValueError("items[].knowledgeType is required before binding isolation keywords")
            client.get_knowledge_by_type(int(knowledge_id), knowledge_type)
            current_bindings = client.get_knowledge_isolation_keywords(int(knowledge_id), knowledge_type)
            if not isinstance(current_bindings, list):
                raise ValueError("existing isolation keyword bindings must be an array")
            current_ids = []
            for binding in current_bindings:
                keyword_id = binding.get("id") if isinstance(binding, dict) else None
                if isinstance(keyword_id, bool) or not isinstance(keyword_id, int) or keyword_id <= 0:
                    raise ValueError("existing isolation keyword bindings contain an invalid ID")
                current_ids.append(keyword_id)

            requested_ids = item.get("keywordIds") if isinstance(item, dict) else None
            if not isinstance(requested_ids, list):
                raise ValueError("items[].keywordIds must be an array")
            if any(
                isinstance(keyword_id, bool)
                or not isinstance(keyword_id, int)
                or keyword_id <= 0
                for keyword_id in requested_ids
            ):
                raise ValueError("items[].keywordIds must contain positive integer IDs")
            if operation == "append":
                final_ids = list(dict.fromkeys([*current_ids, *requested_ids]))
            elif operation == "remove":
                removed_ids = set(requested_ids)
                final_ids = [keyword_id for keyword_id in current_ids if keyword_id not in removed_ids]
            else:
                if data.get("confirmReplace") is not True:
                    raise ValueError("binding replacement requires confirmReplace=true after explicit user confirmation")
                final_ids = list(dict.fromkeys(requested_ids))
            resolved_items.append({**item, "knowledgeType": knowledge_type, "keywordIds": final_ids})

        for directory_id in directory_ids:
            client.list_knowledge(directory_id=int(directory_id), page_size=1000)
        return client.batch_update_isolation_keyword_bindings(
            items=resolved_items,
            directory_ids=directory_ids,
            keyword_ids=data.get("keywordIds"),
        )

    def summary_transcripts():
        result = client.list_transcripts(
            page_size=args.page_size,
            page_index=args.page,
            debug=args.debug,
            begin_ts=args.begin_ts,
            end_ts=args.end_ts,
            touch_point=args.touch_point,
            bot_id=args.bot_id,
            agent_id=args.agent_id,
            intent_id=args.intent_id,
            handoff=handoff,
            keyword=args.keyword or None,
        )
        items = result.get("list", result) if isinstance(result, dict) else result
        if isinstance(items, list):
            compact = [{"chatId": t.get("chatId", t.get("id")),
                        "agentName": t.get("agentName", ""),
                        "touchPoint": t.get("touchPoint", t.get("touchpoint", "")),
                        "handoff": t.get("handoff"), "messageCount": t.get("messageCount"),
                        "externalId": t.get("externId", t.get("externalId", t.get("external_id"))),
                        "createdAt": t.get("createdAt", "")} for t in items]
            if isinstance(result, dict):
                return {
                    "pageIndex": result.get("pageIndex", args.page),
                    "pageSize": result.get("pageSize", args.page_size),
                    "hasNext": bool(result.get("hasNext")),
                    "list": compact,
                }
            return compact
        return result

    def resolve_transcript_chat_id():
        if not args.external_id:
            raise ValueError("resolve-transcript-chat-id requires --external-id")
        return client.resolve_transcript_chat_id(
            args.external_id,
            page_size=args.page_size,
            debug=args.debug,
        )

    def summary_voice_agents():
        agents = client.list_voice_agents()
        if isinstance(agents, list):
            return [{"id": a.get("id"), "name": a.get("name"), "type": a.get("type"),
                     "description": a.get("description", "")} for a in agents]
        return agents

    def summary_voice_transcripts():
        result = client.list_voice_transcripts(
            page_num=args.page, page_size=args.page_size,
            begin_ts=args.begin_ts, end_ts=args.end_ts)
        items = result.get("records", result.get("list", result)) if isinstance(result, dict) else result
        if isinstance(items, list):
            compact = [{"callId": t.get("callId", t.get("chatId", "")),
                        "agentId": t.get("agentId"),
                        "callerNumber": t.get("callerNumber", ""),
                        "callDuration": t.get("callDuration"),
                        "endReason": t.get("endReason", ""),
                        "createdAt": t.get("createdAt", "")} for t in items]




            if isinstance(result, dict):
                return {"total": result.get("total", len(compact)), "list": compact}
            return compact
        return result

    commands = {
        "get_project": lambda: client.get_project_info(),
        "replace_mock_data": replace_mock_data,
        "query_mock_data": query_mock_data,
        "list_agents": summary_agents,
        "get_agent": lambda: client.get_agent(args.id),
        "get_chatflow_graph": lambda: client.get_chatflow_graph(args.agent_id),
        "create_agent": lambda: client.create_agent(load_data()),
        "update_agent": lambda: client.update_agent(load_data()),
        "update_chatflow": update_chatflow,
        "list_plugins": summary_plugins,
        "get_plugin": lambda: client.get_plugin(args.id),
        "create_plugin": lambda: client.create_plugin(load_data()),
        "update_plugin": lambda: client.update_plugin(load_data()),
        "delete_plugin": lambda: client.delete_plugin(args.id),
        "run_plugin": run_plugin,
        "list_ai_fields": lambda: client.list_ai_fields(),
        "list_agent_ai_fields": lambda: client.list_agent_ai_fields(),
        "get_ai_field_guide": lambda: client.get_ai_field_guide_record(),
        "initialize_ai_fields": lambda: client.initialize_ai_fields(),
        "list_managed_ai_fields": lambda: client.list_managed_ai_fields(
            page_index=args.page, page_size=args.page_size, name=args.keyword),
        "get_managed_ai_field": lambda: client.get_managed_ai_field(args.id),
        "create_managed_ai_field": lambda: client.create_managed_ai_field(
            require_object_data("create-managed-ai-field")),
        "update_managed_ai_field": lambda: client.update_managed_ai_field(
            require_object_data("update-managed-ai-field")),
        "delete_managed_ai_field": lambda: client.delete_managed_ai_field(args.id),
        "toggle_managed_ai_field": lambda: client.toggle_managed_ai_field(args.id),
        "get_quality_status": lambda: client.get_quality_inspection_status(),
        "set_quality_status": set_quality_status,
        "list_quality_rules": lambda: client.list_quality_inspection_rules(
            begin_timestamp=args.begin_ts, end_timestamp=args.end_ts),
        "get_quality_rule": lambda: client.get_quality_inspection_rule(
            require_inspection_key("get-quality-rule")),
        "update_quality_rule": lambda: client.update_quality_inspection_rule(
            require_object_data("update-quality-rule")),
        "create_custom_quality_rule": lambda: client.create_custom_quality_rule(
            require_object_data("create-custom-quality-rule")),
        "get_custom_quality_rule": lambda: client.get_custom_quality_rule(
            require_inspection_key("get-custom-quality-rule")),
        "update_custom_quality_rule": lambda: client.update_custom_quality_rule(
            require_object_data("update-custom-quality-rule")),
        "delete_custom_quality_rule": lambda: client.delete_custom_quality_rule(
            require_inspection_key("delete-custom-quality-rule")),
        "list_quality_alert_rules": lambda: client.list_quality_alert_rules(),
        "get_quality_alert_rule": lambda: client.get_quality_alert_rule(args.id),
        "create_quality_alert_rule": lambda: client.create_quality_alert_rule(
            require_object_data("create-quality-alert-rule")),
        "update_quality_alert_rule": lambda: client.update_quality_alert_rule(
            require_object_data("update-quality-alert-rule")),
        "delete_quality_alert_rule": lambda: client.delete_quality_alert_rule(args.id),
        "list_quality_alert_messages": lambda: client.list_quality_alert_messages(
            require_object_data("list-quality-alert-messages")),
        "get_quality_alert_message": lambda: client.get_quality_alert_message(args.id),
        "chat": lambda: client.chat(
            message=args.message, bot_id=args.bot_id, chat_id=args.chat_id,
            touch_point=args.touch_point or "LIVE_CHAT",
            metadata=(load_data() or {}).get("metadata") if (args.data or args.data_file) else None),
        "chat_stream": lambda: client.chat_stream(
            message=args.message, bot_id=args.bot_id, chat_id=args.chat_id,
            touch_point=args.touch_point or "LIVE_CHAT",
            metadata=(load_data() or {}).get("metadata") if (args.data or args.data_file) else None),
        "chat_async": lambda: client.chat_async(
            message=args.message, bot_id=args.bot_id, chat_id=args.chat_id,
            touch_point=args.touch_point or "LIVE_CHAT",
            metadata=(load_data() or {}).get("metadata") if (args.data or args.data_file) else None,
            callback=args.callback, expire_minutes=args.expire_minutes),
        "get_async_result": lambda: client.get_async_result(
            args.receipt, bot_id=args.bot_id),
        "list_strategies": lambda: client.list_strategies(page_size=args.page_size),
        "list_templates": summary_templates,
        "create_template": create_template,
        "update_template": update_template,
        "delete_templates": delete_templates,
        "get_conversations_by_intent": lambda: client.get_conversations_by_intent(
            args.intent, limit=args.limit),
        "list_intents": summary_intents,
        "create_intent": lambda: client.create_intent(load_data()),
        "get_intent": lambda: client.get_intent(args.id),
        "update_intent": lambda: client.update_intent(args.id, load_data()),
        "toggle_intent": lambda: client.toggle_intent(
            args.id, enabled=not args.disable),
        "list_entities": lambda: client.list_entities(),
        "create_strategy": lambda: client.create_strategy(load_data()),
        "update_strategy": lambda: client.update_strategy(args.id, load_data()),
        "toggle_strategy": lambda: client.toggle_strategy(
            args.id, enabled=not args.disable),
        "list_knowledge": summary_knowledge,
        "get_knowledge": get_knowledge,
        "get_knowledge_isolation_keywords": get_knowledge_isolation_keywords,
        "update_knowledge": update_knowledge,
        "batch_update_knowledge": batch_update_knowledge,
        "update_document_content": update_document_content,
        "create_product_knowledge": create_product_knowledge,
        "update_product_knowledge": update_product_knowledge,
        "batch_update_products": batch_update_products,
        "operate_knowledge": operate_knowledge,
        "edit_knowledge_tags": edit_knowledge_tags,
        "list_knowledge_tags": summary_knowledge_tags,
        "upload_qa": lambda: client.upload_qa(load_data()),
        "upload_web": lambda: client.upload_web(args.urls or []),
        "list_directories": summary_directories,
        "create_folder": create_folder,
        "update_directory": update_directory,
        "move_directory": move_directory,
        "delete_directory": delete_directory,
        "list_isolation_keywords": summary_isolation_keywords,
        "create_isolation_keyword": create_isolation_keyword,
        "update_isolation_keyword": update_isolation_keyword,
        "delete_isolation_keyword": delete_isolation_keyword,
        "batch_update_isolation_keyword_bindings": batch_update_isolation_keyword_bindings,
        "list_transcripts": summary_transcripts,
        "get_transcript": lambda: client.get_transcript(args.chat_id),
        "resolve_transcript_chat_id": resolve_transcript_chat_id,
        "get_chat_context": lambda: client.get_chat_context(
            args.bot_id, json.loads(args.data) if args.data else {}
        ),
        "export_transcripts": lambda: client.export_transcripts(
            page_size=args.page_size, page_index=args.page, debug=args.debug,
            begin_ts=args.begin_ts, end_ts=args.end_ts,
            time_offset=args.time_offset),
        "get_export_tasks": lambda: client.get_export_tasks(
            page=args.page, page_size=args.page_size),
        "upload_batch_test_file": lambda: client.upload_batch_test_file(args.file),
        "submit_batch_test": lambda: client.submit_batch_test(
            args.file_key,
            args.task_type,
            bot_id=args.bot_id,
            metadata=(load_data() or {}).get("metadata") if (args.data or args.data_file) else None,
        ),
        "get_batch_test_tasks": lambda: client.get_label_tasks(
            page=args.page, page_size=args.page_size, task_type=args.task_type),
        "list_label_groups": lambda: client.list_label_groups(tree_name=args.name or args.keyword),
        "create_label_group": create_label_group,
        "update_label_group": update_label_group,
        "delete_label_group": lambda: client.delete_label_group(require_id("delete-label-group")),
        "get_label_tree": get_label_tree,
        "get_label_detail_tree": get_label_detail_tree,
        "create_label_node": create_label_node,
        "update_label_node": update_label_node,
        "delete_label_node": delete_label_node,
        "download_label_template": download_label_template,
        "download_labels": download_labels,
        "upload_labels": upload_labels,
        "report_transcript": lambda: client.report_transcript(
            args.begin_ts, args.end_ts, time_offset=args.time_offset,
            bot_id=args.bot_id, touch_point=args.touch_point,
            date_unit=args.date_unit),
        "report_message": lambda: client.report_message(
            args.begin_ts, args.end_ts, time_offset=args.time_offset,
            bot_id=args.bot_id, touch_point=args.touch_point,
            date_unit=args.date_unit),
        "report_agent": lambda: client.report_agent(
            args.begin_ts, args.end_ts, args.time_offset, args.bot_id, args.touch_point,
            args.date_unit, args.agent_id),
        "report_intent": lambda: client.report_intent(
            args.begin_ts, args.end_ts, time_offset=args.time_offset,
            bot_id=args.bot_id, touch_point=args.touch_point,
            intent_id=args.intent_id, date_unit=args.date_unit),
        "report_satisfaction": lambda: client.report_satisfaction_summary(
            args.begin_ts, args.end_ts, args.time_offset, args.bot_id, args.touch_point),
        "report_satisfaction_list": lambda: client.report_satisfaction_list(
            args.begin_ts, args.end_ts, args.time_offset, args.page, args.page_size,
            args.bot_id, args.touch_point, args.assistant_role,
            None if args.satisfied is None else args.satisfied == "true"),
        "report_knowledge": lambda: client.report_knowledge(
            args.begin_ts, args.end_ts, args.time_offset, args.page, args.page_size,
            json.loads(args.sort_by) if args.sort_by else None,
            args.bot_id, args.touch_point, args.source),
        "report_escalation": lambda: client.report_escalation_reasons(
            args.begin_ts, args.end_ts, args.time_offset,
            args.date_unit or "DAY", args.bot_id, args.touch_point),
        "report_livechat": lambda: client.report_livechat_summary(
            args.begin_ts, args.end_ts, args.time_offset),
        "report_livechat_table": lambda: client.report_livechat_table(
            args.begin_ts, args.end_ts, args.time_offset, args.page, args.page_size),
        "report_inspection": lambda: client.report_inspection(
            args.start_date, args.end_date, args.dimension),
        "report_inspection_history": lambda: client.report_inspection_history(
            args.start_date, args.end_date, args.dimension),
        "report_self_learning": lambda: client.report_self_learning(
            args.begin_ts, args.end_ts, args.time_offset, args.bot_id, args.touch_point),
        "report_feedback": lambda: client.report_feedback(
            args.begin_ts, args.end_ts, args.time_offset, args.bot_id, args.touch_point),
        # Modern /chatReport endpoints (the official Agent Analytics page)
        "chat_report_tickets": lambda: client.chat_report(
            "tickets", args.start_date, args.end_date, args.bot_id,
            args.touch_point or args.channel, args.intent_id, args.agent_id),
        "chat_report_messages": lambda: client.chat_report(
            "messages", args.start_date, args.end_date, args.bot_id,
            args.touch_point or args.channel, args.intent_id, args.agent_id),
        "chat_report_intents": lambda: client.chat_report(
            "intents", args.start_date, args.end_date, args.bot_id,
            args.touch_point or args.channel, args.intent_id, args.agent_id),
        "chat_report_agents": lambda: client.chat_report(
            "agents", args.start_date, args.end_date, args.bot_id,
            args.touch_point or args.channel, args.intent_id, args.agent_id),
        "chat_report_satisfaction": lambda: client.chat_report(
            "satisfaction", args.start_date, args.end_date, args.bot_id,
            args.touch_point or args.channel, args.intent_id, args.agent_id),
        "chat_report_first_response": lambda: client.chat_report(
            "first-response", args.start_date, args.end_date, args.bot_id,
            args.touch_point or args.channel, args.intent_id, args.agent_id),
        "chat_report_return_retention": lambda: client.chat_report(
            "return-retention", args.start_date, args.end_date, args.bot_id,
            args.touch_point or args.channel, args.intent_id, args.agent_id),
        "chat_report_inspection_results": lambda: client.chat_report(
            "inspection-results", args.start_date, args.end_date, args.bot_id,
            args.touch_point or args.channel, args.intent_id, args.agent_id),
        "chat_report_inbox_scripts": lambda: client.chat_report_inbox_scripts(),
        # Transitional /dashboard endpoints (kept for backwards compatibility)
        "dashboard_overview": lambda: client.dashboard(
            "overview", args.start_date, args.end_date, args.bot_id, args.channel,
            args.business_type, args.granularity, args.agent_id),
        "dashboard_message_trend": lambda: client.dashboard(
            "message-trend", args.start_date, args.end_date, args.bot_id, args.channel,
            args.business_type, args.granularity, args.agent_id),
        "dashboard_intent_distribution": lambda: client.dashboard(
            "intent-distribution", args.start_date, args.end_date, args.bot_id, args.channel,
            args.business_type, args.granularity, args.agent_id),
        "dashboard_agent_performance": lambda: client.dashboard(
            "agent-performance", args.start_date, args.end_date, args.bot_id, args.channel,
            args.business_type, args.granularity, args.agent_id),
        "dashboard_intent_trend": lambda: client.dashboard(
            "intent-trend", args.start_date, args.end_date, args.bot_id, args.channel,
            args.business_type, args.granularity, args.agent_id),
        "dashboard_agent_trend": lambda: client.dashboard(
            "agent-trend", args.start_date, args.end_date, args.bot_id, args.channel,
            args.business_type, args.granularity, args.agent_id),
        "dashboard_handoff_heatmap": lambda: client.dashboard(
            "handoff-heatmap", args.start_date, args.end_date, args.bot_id, args.channel,
            args.business_type, args.granularity, args.agent_id),
        "dashboard_turn_funnel": lambda: client.dashboard(
            "turn-funnel", args.start_date, args.end_date, args.bot_id, args.channel,
            args.business_type, args.granularity, args.agent_id),
        "dashboard_handoff_chat_ids": lambda: client.dashboard_handoff_chat_ids(
            args.week_start_date, args.primary_reason, args.secondary_reason, args.limit),
        "report_escalation_drilldown": lambda: client.report_escalation_drilldown(
            args.begin_ts, args.end_ts, args.reason, args.time_offset,
            args.page, args.page_size, args.bot_id, args.touch_point),
        "report_agent_weekly_graph": lambda: client.report_agent_weekly_graph(
            args.begin_ts, args.end_ts, args.time_offset),
        # Voice Agent
        "list_voice_agents": summary_voice_agents,
        "list_voice_transcripts": summary_voice_transcripts,
        "get_voice_transcript": lambda: client.get_voice_transcript(args.history_id),
    }

    if cmd not in commands:
        print(f"Unknown command: {args.command}")
        print(f"Available: {', '.join(k.replace('_', '-') for k in commands)}")
        sys.exit(1)

    try:
        result = commands[cmd]()
        output(result)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
