import { pathSegment, sanitize, type ReadCommand } from "./read-client.js";
const CHANNEL_FIELDS = [
  "id",
  "channelType",
  "sellerId",
  "authType",
  "storeAuthStatus",
  "storeName",
  "site",
  "country",
  "region",
  "platform",
  "sellingPartnerId",
  "channelSupportName",
  "status",
  "isDisable",
  "createdAt",
  "updatedAt",
  "botId",
  "brand",
  "personaId",
];
const LINE_FIELDS = ["channelId", "accountName", "brand", "status", "createdAt"];
const WHATSAPP_FIELDS = [
  "channelId",
  "accountName",
  "businessPhone",
  "verifiedName",
  "status",
  "createdAt",
];
const API_SUMMARY_FIELDS = [
  "id",
  "name",
  "description",
  "status",
  "projectId",
  "createdAt",
  "updatedAt",
];
export const integrationCommands: Record<string, ReadCommand> = {
  "connections-list": {
    parameters: { botId: { type: "integer" } },
    async run(client, params) {
      const { botId } = params;

      return sanitize(await client.get("/api_v2/intelli/channels", { params: { botId: botId } }));
    },
  },
  "connections-counts": {
    parameters: { personaId: { type: "integer" } },
    async run(client, params) {
      const { personaId } = params;

      return sanitize(
        await client.get("/api_v2/intelli/channel/count", { params: { personaId: personaId } }),
      );
    },
  },
  "custom-ticket-list": {
    parameters: {},
    async run(client, params) {
      const data = await client.get("/api_v2/intelli/custom-ticket/channels");
      return sanitize(data, CHANNEL_FIELDS, [
        "botId",
        "personaId",
        "accountName",
        "replyFormat",
        "replyTimeoutMs",
        "aiReplyEnabled",
        "replyWhenHandoff",
        "aiTagCallbackEnabled",
        "summaryAsyncEnabled",
        "historyPageSize",
        "formatUserHtmlMessage",
        "inboundCustomFieldMappings",
        "outboundCustomFieldMappings",
      ]);
    },
  },
  "custom-ticket-get": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      const data = await client.get(`/api_v2/intelli/custom-ticket/channels/${pathSegment(id)}`);
      return sanitize(data, CHANNEL_FIELDS, [
        "botId",
        "personaId",
        "accountName",
        "replyFormat",
        "replyTimeoutMs",
        "aiReplyEnabled",
        "replyWhenHandoff",
        "aiTagCallbackEnabled",
        "summaryAsyncEnabled",
        "historyPageSize",
        "formatUserHtmlMessage",
        "inboundCustomFieldMappings",
        "outboundCustomFieldMappings",
      ]);
    },
  },
  "custom-ticket-history-status": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return sanitize(
        await client.get(
          `/api_v2/intelli/custom-ticket/channels/${pathSegment(id)}/learn-history/status`,
        ),
      );
    },
  },
  "custom-ticket-history-progress": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return sanitize(
        await client.get(
          `/api_v2/intelli/custom-ticket/channels/${pathSegment(id)}/learn-history/progress`,
        ),
      );
    },
  },
  "custom-livechat-list": {
    parameters: {},
    async run(client, params) {
      const data = await client.get("/api_v2/intelli/custom-livechat/channels");
      return sanitize(data, CHANNEL_FIELDS, [
        "botId",
        "personaId",
        "accountName",
        "replyFormat",
        "replyTimeoutMs",
        "aiReplyEnabled",
        "replyWhenHandoff",
        "replyBodyMappings",
        "statusNotifyBodyMappings",
        "initialMessage",
      ]);
    },
  },
  "custom-livechat-get": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      const data = await client.get(`/api_v2/intelli/custom-livechat/channels/${pathSegment(id)}`);
      return sanitize(data, CHANNEL_FIELDS, [
        "botId",
        "personaId",
        "accountName",
        "replyFormat",
        "replyTimeoutMs",
        "aiReplyEnabled",
        "replyWhenHandoff",
        "replyBodyMappings",
        "statusNotifyBodyMappings",
        "initialMessage",
      ]);
    },
  },
  "custom-livechat-history-status": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return sanitize(
        await client.get(
          `/api_v2/intelli/custom-livechat/channels/${pathSegment(id)}/learn-history/status`,
        ),
      );
    },
  },
  "custom-livechat-history-progress": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return sanitize(
        await client.get(
          `/api_v2/intelli/custom-livechat/channels/${pathSegment(id)}/learn-history/progress`,
        ),
      );
    },
  },
  "line-list": {
    parameters: {},
    async run(client, params) {
      const data = await client.get("/api_v2/intelli/line/channels");
      return sanitize(data, LINE_FIELDS);
    },
  },
  "line-get": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      const data = await client.get(`/api_v2/intelli/line/channels/${pathSegment(id)}`);
      return sanitize(data, LINE_FIELDS);
    },
  },
  "whatsapp-list": {
    parameters: {},
    async run(client, params) {
      const data = await client.get("/api_v2/intelli/whatsapp/channels");
      return sanitize(data, WHATSAPP_FIELDS);
    },
  },
  "whatsapp-get": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      const data = await client.get(`/api_v2/intelli/whatsapp/channels/${pathSegment(id)}`);
      return sanitize(data, WHATSAPP_FIELDS);
    },
  },
  "custom-data-list": {
    parameters: {},
    async run(client, params) {
      const data = await client.get("/api_v2/intelli/custom-data/channels");
      return sanitize(data, CHANNEL_FIELDS);
    },
  },
  "custom-data-get": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      const data = await client.get(`/api_v2/intelli/custom-data/channels/${pathSegment(id)}`);
      return sanitize(data, CHANNEL_FIELDS);
    },
  },
  "zendesk-settings": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zendesk/setting"));
    },
  },
  "zoho-settings": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zoho/setting"));
    },
  },
  "freshdesk-settings": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/freshdesk/setting"));
    },
  },
  "liveagent-settings": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/liveagent/setting"));
    },
  },
  "sunshine-settings": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/sunshine/setting"));
    },
  },
  "zendesk-agents": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zendesk/agents"));
    },
  },
  "zendesk-views": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zendesk/views"));
    },
  },
  "zendesk-support-addresses": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zendesk/supportAddresses"));
    },
  },
  "zendesk-ticket-fields": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zendesk/ticket-fields"));
    },
  },
  "zendesk-ai-field-mapping": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zendesk/ai-field-mapping"));
    },
  },
  "zendesk-ai-variable-mapping": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zendesk/ai-variable-mapping"));
    },
  },
  "zendesk-ticket-field-mapping": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zendesk/ticket-field-mapping"));
    },
  },
  "zendesk-auth-result": {
    parameters: { attemptId: { type: "string", required: true } },
    async run(client, params) {
      const { attemptId } = params;

      return sanitize(
        await client.get(`/api_v2/intelli/zendesk/auth/result/${pathSegment(attemptId)}`),
      );
    },
  },
  "zendesk-diagnose": {
    parameters: { ticketId: { type: "integer" }, sampleLimit: { type: "integer" } },
    async run(client, params) {
      const { ticketId, sampleLimit } = params;

      if (sampleLimit != null && (sampleLimit < 1 || sampleLimit > 50)) {
        throw new Error("sampleLimit outside supported range");
      }
      return sanitize(
        await client.post("/api_v2/intelli/zendesk/full-chain/test", {
          body: { ticketId: ticketId, sampleLimit: sampleLimit },
        }),
      );
    },
  },
  "zendesk-trace": {
    parameters: { externKeyId: { type: "integer" }, ticketId: { type: "string", required: true } },
    async run(client, params) {
      const { externKeyId, ticketId } = params;

      return sanitize(
        await client.get(`/api_v2/intelli/zendesk/trace/tickets/${pathSegment(ticketId)}`, {
          params: { externKeyId: externKeyId },
        }),
      );
    },
  },
  "zoho-auth-status": {
    parameters: { orgId: { type: "string" } },
    async run(client, params) {
      const { orgId } = params;

      return sanitize(
        await client.get("/api_v2/intelli/zoho/auth/status", { params: { orgId: orgId } }),
      );
    },
  },
  "zoho-bot-binding": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zoho/bot-binding"));
    },
  },
  "zoho-intent-tagging": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zoho/intent-tagging"));
    },
  },
  "zoho-process-rules": {
    parameters: { orgId: { type: "string" } },
    async run(client, params) {
      const { orgId } = params;

      return sanitize(
        await client.get("/api_v2/intelli/zoho/process-rules", { params: { orgId: orgId } }),
      );
    },
  },
  "zoho-ticket-fields": {
    parameters: { orgId: { type: "string" } },
    async run(client, params) {
      const { orgId } = params;

      return sanitize(
        await client.get("/api_v2/intelli/zoho/ticket-fields", { params: { orgId: orgId } }),
      );
    },
  },
  "zoho-departments": {
    parameters: { orgId: { type: "string" } },
    async run(client, params) {
      const { orgId } = params;

      return sanitize(
        await client.get("/api_v2/intelli/zoho/departments", { params: { orgId: orgId } }),
      );
    },
  },
  "zoho-views": {
    parameters: { orgId: { type: "string" }, departmentId: { type: "string" } },
    async run(client, params) {
      const { orgId, departmentId } = params;

      return sanitize(
        await client.get("/api_v2/intelli/zoho/views", {
          params: { orgId: orgId, departmentId: departmentId },
        }),
      );
    },
  },
  "zoho-ai-field-mapping": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zoho/ai-field-mapping"));
    },
  },
  "zoho-ai-field-config": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zoho/ai-field-config"));
    },
  },
  "zoho-ticket-field-mapping": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zoho/ticket-field-mapping"));
    },
  },
  "zoho-custom-field-mapping": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zoho/custom-field-mapping"));
    },
  },
  "zoho-ai-variable-mapping": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zoho/ai-variable-mapping"));
    },
  },
  "zoho-diagnose": {
    parameters: {
      ticketId: { type: "string" },
      orgId: { type: "string" },
      sampleLimit: { type: "integer" },
    },
    async run(client, params) {
      const { ticketId, orgId, sampleLimit } = params;

      if (sampleLimit != null && (sampleLimit < 1 || sampleLimit > 50)) {
        throw new Error("sampleLimit outside supported range");
      }
      return sanitize(
        await client.post("/api_v2/intelli/zoho/full-chain/test", {
          body: { ticketId: ticketId, orgId: orgId, sampleLimit: sampleLimit },
        }),
      );
    },
  },
  "zendesk-history-status": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zendesk/learnHistory/status"));
    },
  },
  "zoho-history-status": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/zoho/learnHistory/status"));
    },
  },
  "sunshine-history-status": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/sunshine/learnHistory/status"));
    },
  },
  "freshdesk-agents": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/freshdesk/agents"));
    },
  },
  "freshdesk-automations": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/freshdesk/automations"));
    },
  },
  "liveagent-agents": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/liveagent/agents"));
    },
  },
  "gmail-list": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/gmail/list"));
    },
  },
  "tiktok-settings": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/tiktok-shop/setting"));
    },
  },
  "tiktok-apps": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/tiktok-shop/apps"));
    },
  },
  "sync-orders": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/job-params/progress"));
    },
  },
  "sync-products": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/job-params/product/progress"));
    },
  },
  "sync-catalog": {
    parameters: { projectId: { type: "integer", required: true } },
    async run(client, params) {
      const { projectId } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/products/fullSync/process", {
          params: { projectId: projectId },
        }),
      );
    },
  },
  "custom-ticket-docs": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/custom-ticket/integration-docs"));
    },
  },
  "email-list": {
    parameters: { keyword: { type: "string" } },
    async run(client, params) {
      const { keyword } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/email/list", { params: { keyword: keyword } }),
      );
    },
  },
  "amazon-list": {
    parameters: { keyword: { type: "string" } },
    async run(client, params) {
      const { keyword } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/amazon/list", { params: { keyword: keyword } }),
      );
    },
  },
  "ebay-list": {
    parameters: { keyword: { type: "string" } },
    async run(client, params) {
      const { keyword } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/ebay/list", { params: { keyword: keyword } }),
      );
    },
  },
  "shopify-list": {
    parameters: { keyword: { type: "string" }, personaId: { type: "integer" } },
    async run(client, params) {
      const { keyword, personaId } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/shopify/list", {
          params: { keyword: keyword, personaId: personaId },
        }),
      );
    },
  },
  "walmart-list": {
    parameters: { keyword: { type: "string" } },
    async run(client, params) {
      const { keyword } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/walmart/list", { params: { keyword: keyword } }),
      );
    },
  },
  "rakuten-list": {
    parameters: { keyword: { type: "string" } },
    async run(client, params) {
      const { keyword } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/rakuten/list", { params: { keyword: keyword } }),
      );
    },
  },
  "email-get": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/email/details", { params: { id: id } }),
      );
    },
  },
  "amazon-get": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/amazon/details", { params: { id: id } }),
      );
    },
  },
  "ebay-get": {
    parameters: { state: { type: "string", required: true } },
    async run(client, params) {
      const { state } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/ebay/details", { params: { state: state } }),
      );
    },
  },
  "shopify-get": {
    parameters: { state: { type: "string", required: true }, personaId: { type: "integer" } },
    async run(client, params) {
      const { state, personaId } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/shopify/details", {
          params: { state: state, personaId: personaId },
        }),
      );
    },
  },
  "email-folders": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return sanitize(
        await client.get("/api_v2/tars/api/channel/email/get_email_folder", { params: { id: id } }),
      );
    },
  },
  "shopline-list": {
    parameters: { keyword: { type: "string" } },
    async run(client, params) {
      const { keyword } = params;

      return sanitize(
        await client.get("/api_v2/intelli/shopline/extern-keys", { params: { keyword: keyword } }),
      );
    },
  },
  "shopline-get": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return sanitize(await client.get(`/api_v2/intelli/shopline/extern-keys/${pathSegment(id)}`));
    },
  },
  "shopify-countries": {
    parameters: { channelId: { type: "string", required: true } },
    async run(client, params) {
      const { channelId } = params;

      return sanitize(
        await client.get(
          `/api_v2/intelli/shopify/channels/${pathSegment(channelId)}/serving-countries`,
        ),
      );
    },
  },
  "shulex-ticket-status": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/ticket/tars-ai-reply/status"));
    },
  },
  "shulex-ticket-emails": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/ticket/tars-ai-reply/support-emails"));
    },
  },
  "api-list": {
    parameters: { projectId: { type: "integer", required: true } },
    async run(client, params) {
      const { projectId } = params;

      const data = await client.get("/api_v2/intelli/custom-api/listBrief", {
        params: { projectId: projectId },
      });
      return sanitize(data, API_SUMMARY_FIELDS);
    },
  },
  "livechat-list": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/intelli/livechat/bot"));
    },
  },
  "livechat-config": {
    parameters: {
      source: { type: "string", default: "backend" },
      t: { type: "integer" },
      botId: { type: "string", required: true },
    },
    async run(client, params) {
      const { source, t, botId } = params;

      return sanitize(
        await client.get(`/api_v2/gpt/bot/${pathSegment(botId)}/livechat/config`, {
          params: { source: source, t: t },
        }),
      );
    },
  },
  "livechat-setup": {
    parameters: { botId: { type: "string", required: true } },
    async run(client, params) {
      const { botId } = params;

      return sanitize(await client.get(`/api_v2/gpt/bot/${pathSegment(botId)}/setup`));
    },
  },
  "phone-list": {
    parameters: {
      search: { type: "string" },
      page: { type: "integer", default: 1 },
      limit: { type: "integer", default: 50 },
      projectId: { type: "string", required: true },
    },
    async run(client, params) {
      const { search, page, limit, projectId } = params;

      if (page != null && page < 1) {
        throw new Error("page outside supported range");
      }

      if (limit != null && (limit < 1 || limit > 50)) {
        throw new Error("limit outside supported range");
      }

      return sanitize(
        await client.post(
          `/api_v2/gpt/voice/projectId/${pathSegment(projectId)}/phone-number/list`,
          { body: { search: search, page: page, limit: limit } },
        ),
      );
    },
  },
  "phone-get": {
    parameters: {
      projectId: { type: "string", required: true },
      phoneId: { type: "string", required: true },
    },
    async run(client, params) {
      const { projectId, phoneId } = params;

      return sanitize(
        await client.get(
          `/api_v2/gpt/voice/projectId/${pathSegment(projectId)}/phone-number/${pathSegment(phoneId)}`,
        ),
      );
    },
  },
};
