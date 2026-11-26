import { pathSegment, sanitize, type ReadCommand } from "./read-client.js";

export const ticketCommands: Record<string, ReadCommand> = {
  list: {
    parameters: {
      viewId: { type: "integer" },
      ticketNumber: { type: "string" },
      ticketStatusList: { type: "string[]" },
      channelList: { type: "string[]" },
      platformList: { type: "string[]" },
      channelIdList: { type: "integer[]" },
      supportEmailIdList: { type: "integer[]" },
      agentIdList: { type: "integer[]" },
      tagList: { type: "integer[]" },
      replyUserList: { type: "integer[]" },
      customerEmail: { type: "string" },
      customerName: { type: "string" },
      customerEmailFull: { type: "string" },
      customerPhone: { type: "string" },
      createTimeBegin: { type: "string" },
      createTimeEnd: { type: "string" },
      createTimeBeginMillis: { type: "integer" },
      createTimeEndMillis: { type: "integer" },
      satisfactionSubmitTimeBegin: { type: "string" },
      satisfactionSubmitTimeEnd: { type: "string" },
      satisfactionSubmitTimeBeginMillis: { type: "integer" },
      satisfactionSubmitTimeEndMillis: { type: "integer" },
      keyword: { type: "string" },
      marketList: { type: "string[]" },
      sendFailure: { type: "boolean" },
      orderId: { type: "string" },
      categoryList: { type: "string[]" },
      brandList: { type: "string[]" },
      humanHandling: { type: "boolean" },
      myTicket: { type: "boolean" },
      snoozed: { type: "boolean" },
      scheduled: { type: "boolean" },
      notSpam: { type: "boolean" },
      notNotification: { type: "boolean" },
      botIdList: { type: "integer[]" },
      noTag: { type: "boolean" },
      ticketNumberList: { type: "string[]" },
      supportPhoneList: { type: "string[]" },
      unread: { type: "boolean" },
      personaId: { type: "integer" },
      slaV1StatusList: { type: "string[]" },
      slaV1MetricTypeList: { type: "string[]" },
      slaV1PriorityList: { type: "string[]" },
      campaignName: { type: "string" },
      lastVoiceAnswerType: { type: "string" },
      lastVoicePhoneType: { type: "string" },
      page: { type: "integer", default: 1 },
      pageSize: { type: "integer", default: 50 },
      sort: { type: "string", default: "last_update_time" },
      order: { type: "string", default: "DESC" },
    },
    async run(client, params) {
      const {
        viewId,
        ticketNumber,
        ticketStatusList,
        channelList,
        platformList,
        channelIdList,
        supportEmailIdList,
        agentIdList,
        tagList,
        replyUserList,
        customerEmail,
        customerName,
        customerEmailFull,
        customerPhone,
        createTimeBegin,
        createTimeEnd,
        createTimeBeginMillis,
        createTimeEndMillis,
        satisfactionSubmitTimeBegin,
        satisfactionSubmitTimeEnd,
        satisfactionSubmitTimeBeginMillis,
        satisfactionSubmitTimeEndMillis,
        keyword,
        marketList,
        sendFailure,
        orderId,
        categoryList,
        brandList,
        humanHandling,
        myTicket,
        snoozed,
        scheduled,
        notSpam,
        notNotification,
        botIdList,
        noTag,
        ticketNumberList,
        supportPhoneList,
        unread,
        personaId,
        slaV1StatusList,
        slaV1MetricTypeList,
        slaV1PriorityList,
        campaignName,
        lastVoiceAnswerType,
        lastVoicePhoneType,
        page,
        pageSize,
        sort,
        order,
      } = params;

      if (page != null && page < 1) {
        throw new Error("page outside supported range");
      }

      if (pageSize != null && (pageSize < 1 || pageSize > 100)) {
        throw new Error("pageSize outside supported range");
      }

      return await client.pages("POST", "/api_v2/tars/api/ticket/list", {
        body: {
          viewId: viewId,
          ticketNumber: ticketNumber,
          ticketStatusList: ticketStatusList,
          channelList: channelList,
          platformList: platformList,
          channelIdList: channelIdList,
          supportEmailIdList: supportEmailIdList,
          agentIdList: agentIdList,
          tagList: tagList,
          replyUserList: replyUserList,
          customerEmail: customerEmail,
          customerName: customerName,
          customerEmailFull: customerEmailFull,
          customerPhone: customerPhone,
          createTimeBegin: createTimeBegin,
          createTimeEnd: createTimeEnd,
          createTimeBeginMillis: createTimeBeginMillis,
          createTimeEndMillis: createTimeEndMillis,
          satisfactionSubmitTimeBegin: satisfactionSubmitTimeBegin,
          satisfactionSubmitTimeEnd: satisfactionSubmitTimeEnd,
          satisfactionSubmitTimeBeginMillis: satisfactionSubmitTimeBeginMillis,
          satisfactionSubmitTimeEndMillis: satisfactionSubmitTimeEndMillis,
          keyword: keyword,
          marketList: marketList,
          sendFailure: sendFailure,
          orderId: orderId,
          categoryList: categoryList,
          brandList: brandList,
          humanHandling: humanHandling,
          myTicket: myTicket,
          snoozed: snoozed,
          scheduled: scheduled,
          notSpam: notSpam,
          notNotification: notNotification,
          botIdList: botIdList,
          noTag: noTag,
          ticketNumberList: ticketNumberList,
          supportPhoneList: supportPhoneList,
          unread: unread,
          personaId: personaId,
          slaV1StatusList: slaV1StatusList,
          slaV1MetricTypeList: slaV1MetricTypeList,
          slaV1PriorityList: slaV1PriorityList,
          campaignName: campaignName,
          lastVoiceAnswerType: lastVoiceAnswerType,
          lastVoicePhoneType: lastVoicePhoneType,
          page: page,
          pageSize: pageSize,
          sort: sort,
          order: order,
        },
        items_key: "list",
        page_key: "page",
        size_key: "pageSize",
      });
    },
  },
  get: {
    parameters: { ticketNumber: { type: "string", required: true } },
    async run(client, params) {
      const { ticketNumber } = params;

      return await client.get(`/api_v2/tars/api/ticket/v2/d/${pathSegment(ticketNumber)}`);
    },
  },
  messages: {
    parameters: {
      before: { type: "string" },
      limit: { type: "integer", default: 50 },
      ticketNumber: { type: "string", required: true },
    },
    async run(client, params) {
      const { before, limit, ticketNumber } = params;

      if (limit != null && (limit < 1 || limit > 100)) {
        throw new Error("limit outside supported range");
      }

      return await client.pages(
        "GET",
        `/api_v2/tars/api/ticket/v2/content/${pathSegment(ticketNumber)}`,
        {
          params: { before: before, limit: limit },
          items_key: "items",
          page_key: "before",
          size_key: "limit",
          cursor: true,
        },
      );
    },
  },
  notes: {
    parameters: { ticketNumber: { type: "string", required: true } },
    async run(client, params) {
      const { ticketNumber } = params;

      return await client.get(
        `/api_v2/tars/api/ticket/v2/content/${pathSegment(ticketNumber)}/notes`,
      );
    },
  },
  "message-origin": {
    parameters: {
      ticketNumber: { type: "string", required: true },
      messageId: { type: "string", required: true },
    },
    async run(client, params) {
      const { ticketNumber, messageId } = params;

      return await client.get(
        `/api_v2/tars/api/ticket/v2/content/${pathSegment(ticketNumber)}/message/${pathSegment(messageId)}/origin`,
      );
    },
  },
  "response-content": {
    parameters: {
      ticketNumber: { type: "string", required: true },
      responseId: { type: "string", required: true },
    },
    async run(client, params) {
      const { ticketNumber, responseId } = params;

      return await client.get(
        `/api_v2/tars/api/ticket/v2/content/${pathSegment(ticketNumber)}/response/${pathSegment(responseId)}/full-content`,
      );
    },
  },
  previous: {
    parameters: { ticketNumber: { type: "string", required: true } },
    async run(client, params) {
      const { ticketNumber } = params;

      return await client.get(`/api_v2/tars/api/ticket/v2/previous/${pathSegment(ticketNumber)}`);
    },
  },
  orders: {
    parameters: { ticketNumber: { type: "string", required: true } },
    async run(client, params) {
      const { ticketNumber } = params;

      return await client.get(`/api_v2/tars/api/ticket/order/${pathSegment(ticketNumber)}`);
    },
  },
  "channel-status": {
    parameters: { ticketNumber: { type: "string", required: true } },
    async run(client, params) {
      const { ticketNumber } = params;

      return await client.get(
        `/api_v2/tars/api/ticket/channel-auth-infos/${pathSegment(ticketNumber)}`,
      );
    },
  },
  "channel-errors": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/ticket/channel-auth-errors");
    },
  },
  tags: {
    parameters: { ticketNum: { type: "string", required: true } },
    async run(client, params) {
      const { ticketNum } = params;

      return await client.get("/api_v2/tars/api/tags/ticket_tags", {
        params: { ticketNum: ticketNum },
      });
    },
  },
  fields: {
    parameters: { ticketNum: { type: "string", required: true } },
    async run(client, params) {
      const { ticketNum } = params;

      return await client.get("/api_v2/tars/api/custom/field/ticket/list", {
        params: { ticketNum: ticketNum },
      });
    },
  },
  activity: {
    parameters: { ticket_number: { type: "string", required: true } },
    async run(client, params) {
      const { ticket_number } = params;

      return await client.get("/api_v2/tars/api/operation-log/get", {
        params: { ticket_number: ticket_number },
      });
    },
  },
  logistics: {
    parameters: {
      orderNumber: { type: "string", required: true },
      trackingNumber: { type: "string", required: true },
    },
    async run(client, params) {
      const { orderNumber, trackingNumber } = params;

      return await client.get("/api_v2/tars/api/ticket/order/logistics", {
        params: { orderNumber: orderNumber, trackingNumber: trackingNumber },
      });
    },
  },
  attachment: {
    parameters: {
      messageId: { type: "string", required: true },
      ticketId: { type: "string", required: true },
      type: { type: "string", required: true },
    },
    async run(client, params) {
      const { messageId, ticketId, type } = params;

      return await client.get("/api_v2/tars/api/ticket/attachment/download", {
        params: { messageId: messageId, ticketId: ticketId, type: type },
      });
    },
  },
  "tags-batch": {
    parameters: { ticketIdList: { type: "integer[]", required: true } },
    async run(client, params) {
      const { ticketIdList } = params;

      return await client.post("/api_v2/tars/api/tags/new/getTags", {
        body: { ticketIdList: ticketIdList },
      });
    },
  },
  related: {
    parameters: {
      customerId: { type: "integer", required: true },
      ticketNumber: { type: "string", required: true },
      page: { type: "integer", default: 1 },
      pageSize: { type: "integer", default: 50 },
      sort: { type: "string", default: "create_time" },
      order: { type: "string", default: "DESC" },
    },
    async run(client, params) {
      const { customerId, ticketNumber, page, pageSize, sort, order } = params;

      if (page != null && page < 1) {
        throw new Error("page outside supported range");
      }

      if (pageSize != null && (pageSize < 1 || pageSize > 100)) {
        throw new Error("pageSize outside supported range");
      }

      return await client.pages("POST", "/api_v2/tars/api/ticket/relate", {
        body: {
          customerId: customerId,
          ticketNumber: ticketNumber,
          page: page,
          pageSize: pageSize,
          sort: sort,
          order: order,
        },
        items_key: "list",
        page_key: "page",
        size_key: "pageSize",
      });
    },
  },
  "sla-projection": {
    parameters: { ticketId: { type: "string", required: true } },
    async run(client, params) {
      const { ticketId } = params;

      return await client.get(`/api_v2/tars/api/sla/tickets/${pathSegment(ticketId)}/projection`);
    },
  },
  "sla-metrics": {
    parameters: { ticketId: { type: "string", required: true } },
    async run(client, params) {
      const { ticketId } = params;

      return await client.get(`/api_v2/tars/api/sla/tickets/${pathSegment(ticketId)}/metrics`);
    },
  },
  "sla-events": {
    parameters: { ticketId: { type: "string", required: true } },
    async run(client, params) {
      const { ticketId } = params;

      return await client.get(`/api_v2/tars/api/sla/tickets/${pathSegment(ticketId)}/events`);
    },
  },
  satisfaction: {
    parameters: { ticketId: { type: "string", required: true } },
    async run(client, params) {
      const { ticketId } = params;

      return await client.get(`/api_v2/tars/api/satisfaction/tickets/${pathSegment(ticketId)}`);
    },
  },
  "conversation-satisfaction": {
    parameters: {
      projectId: { type: "integer", required: true },
      chatId: { type: "string", required: true },
    },
    async run(client, params) {
      const { projectId, chatId } = params;

      return await client.get("/api_v2/gpt/transcript/satisfaction/customer", {
        params: { projectId: projectId, chatId: chatId },
      });
    },
  },
  recording: {
    parameters: {
      voiceCallId: { type: "string", required: true },
      artifactId: { type: "string", required: true },
    },
    async run(client, params) {
      const { voiceCallId, artifactId } = params;

      return await client.get(
        `/api_v2/tars/api/voice/v2/calls/${pathSegment(voiceCallId)}/recordings/${pathSegment(artifactId)}/download`,
      );
    },
  },
  "shopify-order": {
    parameters: {
      channelAuthId: { type: "integer", required: true },
      shopifyOrderId: { type: "string", required: true },
    },
    async run(client, params) {
      const { channelAuthId, shopifyOrderId } = params;

      return await client.get("/api_v2/tars/api/ticket/order/shopify/action/order", {
        params: { channelAuthId: channelAuthId, shopifyOrderId: shopifyOrderId },
      });
    },
  },
  "shopify-order-name": {
    parameters: {
      channelAuthId: { type: "integer", required: true },
      shopifyOrderName: { type: "string", required: true },
    },
    async run(client, params) {
      const { channelAuthId, shopifyOrderName } = params;

      return await client.get("/api_v2/tars/api/ticket/order/shopify/action/order/name", {
        params: { channelAuthId: channelAuthId, shopifyOrderName: shopifyOrderName },
      });
    },
  },
  "batch-failures": {
    parameters: { taskId: { type: "string", required: true } },
    async run(client, params) {
      const { taskId } = params;

      return await client.get(
        `/api_v2/tars/api/ticket/create/batch/tasks/${pathSegment(taskId)}/failures`,
      );
    },
  },
  batches: {
    parameters: {
      startCreatedAt: { type: "string" },
      endCreatedAt: { type: "string" },
      creatorId: { type: "integer" },
      assigneeId: { type: "integer" },
      subject: { type: "string" },
      status: { type: "string" },
      page: { type: "integer", default: 1 },
      pageSize: { type: "integer", default: 50 },
      sort: { type: "string" },
      order: { type: "string" },
    },
    async run(client, params) {
      const {
        startCreatedAt,
        endCreatedAt,
        creatorId,
        assigneeId,
        subject,
        status,
        page,
        pageSize,
        sort,
        order,
      } = params;

      if (page != null && page < 1) {
        throw new Error("page outside supported range");
      }

      if (pageSize != null && (pageSize < 1 || pageSize > 100)) {
        throw new Error("pageSize outside supported range");
      }

      return await client.pages("POST", "/api_v2/tars/api/ticket/create/batch/tasks", {
        body: {
          startCreatedAt: startCreatedAt,
          endCreatedAt: endCreatedAt,
          creatorId: creatorId,
          assigneeId: assigneeId,
          subject: subject,
          status: status,
          page: page,
          pageSize: pageSize,
          sort: sort,
          order: order,
        },
        items_key: "list",
        page_key: "page",
        size_key: "pageSize",
      });
    },
  },
  "customers-list": {
    parameters: {
      keyword: { type: "string" },
      personaId: { type: "integer" },
      emotionType: { type: "string" },
      sortOrder: { type: "string", default: "desc" },
      pageNum: { type: "integer", default: 1 },
      pageSize: { type: "integer", default: 50 },
    },
    async run(client, params) {
      const { keyword, personaId, emotionType, sortOrder, pageNum, pageSize } = params;

      if (pageNum != null && pageNum < 1) {
        throw new Error("pageNum outside supported range");
      }

      if (pageSize != null && (pageSize < 1 || pageSize > 100)) {
        throw new Error("pageSize outside supported range");
      }
      return await client.pages("GET", "/api_v2/tars/api/customer/plg/list", {
        params: {
          keyword: keyword,
          personaId: personaId,
          emotionType: emotionType,
          sortOrder: sortOrder,
          pageNum: pageNum,
          pageSize: pageSize,
        },
        items_key: "records",
        page_key: "pageNum",
        size_key: "pageSize",
      });
    },
  },
  "customers-get": {
    parameters: { customerId: { type: "string", required: true } },
    async run(client, params) {
      const { customerId } = params;

      return await client.get(`/api_v2/tars/api/customer/plg/${pathSegment(customerId)}/detail`);
    },
  },
  "customers-import-current": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/customer/plg/import/task/current");
    },
  },
  "customers-import-task": {
    parameters: { taskId: { type: "string", required: true } },
    async run(client, params) {
      const { taskId } = params;

      return await client.get(`/api_v2/tars/api/customer/plg/import/task/${pathSegment(taskId)}`);
    },
  },
  "catalog-users": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/user/list");
    },
  },
  "catalog-assignable-users": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/user/assign_list");
    },
  },
  "catalog-channels": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/channel-auth/types");
    },
  },
  "catalog-stores": {
    parameters: { channel: { type: "string" } },
    async run(client, params) {
      const { channel } = params;

      return await client.get("/api_v2/tars/api/channel-auth/types/store", {
        params: { channel: channel },
      });
    },
  },
  "catalog-emails": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/channel-auth/types/support-email");
    },
  },
  "catalog-phones": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/channel-auth/types/support-phone");
    },
  },
  "catalog-platforms": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/channel-auth/types/ecomm-platform");
    },
  },
  "catalog-markets": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/channel-auth/types/market");
    },
  },
  "catalog-brands": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/channel/account/brands");
    },
  },
  "catalog-categories": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/field/category/list");
    },
  },
  "catalog-skus": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/field/sku/list");
    },
  },
  "catalog-tags": {
    parameters: { name: { type: "string" } },
    async run(client, params) {
      const { name } = params;

      return await client.get("/api_v2/tars/api/tags/list", { params: { name: name } });
    },
  },
  "catalog-tag-search": {
    parameters: { tagName: { type: "string", required: true } },
    async run(client, params) {
      const { tagName } = params;

      return await client.get("/api_v2/tars/api/tags/new/find", { params: { tagName: tagName } });
    },
  },
  "catalog-fields": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/custom/field/list");
    },
  },
  "reports-overview": {
    parameters: {
      timezone: { type: "string" },
      startDate: { type: "string" },
      endDate: { type: "string" },
      startTime: { type: "string" },
      endTime: { type: "string" },
      channelList: { type: "string[]" },
      agentIdList: { type: "integer[]" },
      supportEmailIdList: { type: "integer[]" },
      platformList: { type: "string[]" },
      channelIdList: { type: "integer[]" },
      dateType: { type: "string" },
      replyAgentQueryType: { type: "string" },
      queryMetrics: { type: "string" },
      dataType: { type: "string" },
    },
    async run(client, params) {
      const {
        timezone,
        startDate,
        endDate,
        startTime,
        endTime,
        channelList,
        agentIdList,
        supportEmailIdList,
        platformList,
        channelIdList,
        dateType,
        replyAgentQueryType,
        queryMetrics,
        dataType,
      } = params;

      return await client.post("/api_v2/tars/api/ticket-report/overview", {
        body: {
          timezone: timezone,
          startDate: startDate,
          endDate: endDate,
          startTime: startTime,
          endTime: endTime,
          channelList: channelList,
          agentIdList: agentIdList,
          supportEmailIdList: supportEmailIdList,
          platformList: platformList,
          channelIdList: channelIdList,
          dateType: dateType,
          replyAgentQueryType: replyAgentQueryType,
          queryMetrics: queryMetrics,
          dataType: dataType,
        },
      });
    },
  },
  "reports-growth": {
    parameters: {
      timezone: { type: "string" },
      startDate: { type: "string" },
      endDate: { type: "string" },
      startTime: { type: "string" },
      endTime: { type: "string" },
      channelList: { type: "string[]" },
      agentIdList: { type: "integer[]" },
      supportEmailIdList: { type: "integer[]" },
      platformList: { type: "string[]" },
      channelIdList: { type: "integer[]" },
      dateType: { type: "string", required: true },
      replyAgentQueryType: { type: "string" },
      queryMetrics: { type: "string", required: true },
      dataType: { type: "string" },
    },
    async run(client, params) {
      const {
        timezone,
        startDate,
        endDate,
        startTime,
        endTime,
        channelList,
        agentIdList,
        supportEmailIdList,
        platformList,
        channelIdList,
        dateType,
        replyAgentQueryType,
        queryMetrics,
        dataType,
      } = params;

      return await client.post("/api_v2/tars/api/ticket-report/new-data", {
        body: {
          timezone: timezone,
          startDate: startDate,
          endDate: endDate,
          startTime: startTime,
          endTime: endTime,
          channelList: channelList,
          agentIdList: agentIdList,
          supportEmailIdList: supportEmailIdList,
          platformList: platformList,
          channelIdList: channelIdList,
          dateType: dateType,
          replyAgentQueryType: replyAgentQueryType,
          queryMetrics: queryMetrics,
          dataType: dataType,
        },
      });
    },
  },
  "reports-responses": {
    parameters: {
      timezone: { type: "string" },
      startDate: { type: "string" },
      endDate: { type: "string" },
      startTime: { type: "string" },
      endTime: { type: "string" },
      channelList: { type: "string[]" },
      agentIdList: { type: "integer[]" },
      supportEmailIdList: { type: "integer[]" },
      platformList: { type: "string[]" },
      channelIdList: { type: "integer[]" },
      dateType: { type: "string", required: true },
      replyAgentQueryType: { type: "string" },
      queryMetrics: { type: "string" },
      dataType: { type: "string" },
    },
    async run(client, params) {
      const {
        timezone,
        startDate,
        endDate,
        startTime,
        endTime,
        channelList,
        agentIdList,
        supportEmailIdList,
        platformList,
        channelIdList,
        dateType,
        replyAgentQueryType,
        queryMetrics,
        dataType,
      } = params;

      return await client.post("/api_v2/tars/api/ticket-report/response", {
        body: {
          timezone: timezone,
          startDate: startDate,
          endDate: endDate,
          startTime: startTime,
          endTime: endTime,
          channelList: channelList,
          agentIdList: agentIdList,
          supportEmailIdList: supportEmailIdList,
          platformList: platformList,
          channelIdList: channelIdList,
          dateType: dateType,
          replyAgentQueryType: replyAgentQueryType,
          queryMetrics: queryMetrics,
          dataType: dataType,
        },
      });
    },
  },
  "reports-performance-v1": {
    parameters: {
      timezone: { type: "string" },
      startDate: { type: "string" },
      endDate: { type: "string" },
      startTime: { type: "string" },
      endTime: { type: "string" },
      channelList: { type: "string[]" },
      agentIdList: { type: "integer[]" },
      supportEmailIdList: { type: "integer[]" },
      platformList: { type: "string[]" },
      channelIdList: { type: "integer[]" },
      dateType: { type: "string" },
      replyAgentQueryType: { type: "string" },
      queryMetrics: { type: "string" },
      dataType: { type: "string" },
    },
    async run(client, params) {
      const {
        timezone,
        startDate,
        endDate,
        startTime,
        endTime,
        channelList,
        agentIdList,
        supportEmailIdList,
        platformList,
        channelIdList,
        dateType,
        replyAgentQueryType,
        queryMetrics,
        dataType,
      } = params;

      return await client.post("/api_v2/tars/api/ticket-report/reply-agent", {
        body: {
          timezone: timezone,
          startDate: startDate,
          endDate: endDate,
          startTime: startTime,
          endTime: endTime,
          channelList: channelList,
          agentIdList: agentIdList,
          supportEmailIdList: supportEmailIdList,
          platformList: platformList,
          channelIdList: channelIdList,
          dateType: dateType,
          replyAgentQueryType: replyAgentQueryType,
          queryMetrics: queryMetrics,
          dataType: dataType,
        },
      });
    },
  },
  "reports-performance-v2": {
    parameters: {
      timezone: { type: "string", required: true },
      startDate: { type: "string" },
      endDate: { type: "string" },
      startTime: { type: "string" },
      endTime: { type: "string" },
      channelList: { type: "string[]" },
      agentIdList: { type: "integer[]" },
      supportEmailIdList: { type: "integer[]" },
      platformList: { type: "string[]" },
      channelIdList: { type: "integer[]" },
      dateType: { type: "string" },
      replyAgentQueryType: { type: "string" },
      queryMetrics: { type: "string" },
      dataType: { type: "string" },
    },
    async run(client, params) {
      const {
        timezone,
        startDate,
        endDate,
        startTime,
        endTime,
        channelList,
        agentIdList,
        supportEmailIdList,
        platformList,
        channelIdList,
        dateType,
        replyAgentQueryType,
        queryMetrics,
        dataType,
      } = params;

      return await client.post("/api_v2/tars/api/ticket-report/reply-agent/v2", {
        body: {
          timezone: timezone,
          startDate: startDate,
          endDate: endDate,
          startTime: startTime,
          endTime: endTime,
          channelList: channelList,
          agentIdList: agentIdList,
          supportEmailIdList: supportEmailIdList,
          platformList: platformList,
          channelIdList: channelIdList,
          dateType: dateType,
          replyAgentQueryType: replyAgentQueryType,
          queryMetrics: queryMetrics,
          dataType: dataType,
        },
      });
    },
  },
  "reports-today": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/ticket-report/today");
    },
  },
  "reports-freshness": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/ticket-report/stat-log");
    },
  },
  "reports-options": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/rpt-dashboard/options");
    },
  },
  "reports-queues": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/routing/monitoring/snapshot");
    },
  },
  "reports-waiting": {
    parameters: { queueId: { type: "string", required: true } },
    async run(client, params) {
      const { queueId } = params;

      return await client.get(
        `/api_v2/tars/api/routing/monitoring/queues/${pathSegment(queueId)}/waiting`,
      );
    },
  },
  "reports-raw": {
    parameters: {
      startTime: { type: "string", required: true },
      endTime: { type: "string", required: true },
      timeRangeType: { type: "string" },
      page: { type: "integer", default: 1 },
      pageSize: { type: "integer", default: 200 },
    },
    async run(client, params) {
      const { startTime, endTime, timeRangeType, page, pageSize } = params;

      if (
        timeRangeType != null &&
        !["report_activity_date", "created_at"].includes(timeRangeType)
      ) {
        throw new Error(
          "invalid timeRangeType; expected one of ['report_activity_date', 'created_at']",
        );
      }

      if (page != null && page < 1) {
        throw new Error("page outside supported range");
      }

      if (pageSize != null && (pageSize < 1 || pageSize > 200)) {
        throw new Error("pageSize outside supported range");
      }
      return await client.pages("POST", "/api_v2/tars/api/ticket/report/raw/page", {
        body: {
          startTime: startTime,
          endTime: endTime,
          timeRangeType: timeRangeType,
          page: page,
          pageSize: pageSize,
        },
        items_key: "list",
        page_key: "page",
        size_key: "pageSize",
      });
    },
  },
  "reports-dashboard": {
    parameters: {
      startDate: { type: "string" },
      endDate: { type: "string" },
      teamIdList: { type: "integer[]" },
      agentIdList: { type: "integer[]" },
      brandIdList: { type: "integer[]" },
      brandNameList: { type: "string[]" },
      channelList: { type: "string[]" },
      platformList: { type: "string[]" },
      channelIdList: { type: "integer[]" },
      supportEmailIdList: { type: "integer[]" },
      ticketTypeIdList: { type: "integer[]" },
      livechatTypeList: { type: "string[]" },
      phoneNumberList: { type: "string[]" },
      voiceDirectionList: { type: "string[]" },
      voiceTypeList: { type: "string[]" },
      completionStatusList: { type: "string[]" },
      initiatorTypeList: { type: "string[]" },
      assignmentStatusList: { type: "string[]" },
      slaPolicyIdList: { type: "integer[]" },
      slaMetricTypeList: { type: "string[]" },
      groupField: { type: "string" },
      dimensionType: { type: "string" },
      dateGrain: { type: "string" },
      pageNum: { type: "integer" },
      pageSize: { type: "integer" },
      keyword: { type: "string" },
      sortField: { type: "string" },
      sortOrder: { type: "string" },
      domain: { type: "string", required: true },
      tabKey: { type: "string", required: true },
    },
    async run(client, params) {
      const {
        startDate,
        endDate,
        teamIdList,
        agentIdList,
        brandIdList,
        brandNameList,
        channelList,
        platformList,
        channelIdList,
        supportEmailIdList,
        ticketTypeIdList,
        livechatTypeList,
        phoneNumberList,
        voiceDirectionList,
        voiceTypeList,
        completionStatusList,
        initiatorTypeList,
        assignmentStatusList,
        slaPolicyIdList,
        slaMetricTypeList,
        groupField,
        dimensionType,
        dateGrain,
        pageNum,
        pageSize,
        keyword,
        sortField,
        sortOrder,
        domain,
        tabKey,
      } = params;

      if (pageNum != null && pageNum < 1) {
        throw new Error("pageNum outside supported range");
      }

      if (pageSize != null && (pageSize < 1 || pageSize > 100)) {
        throw new Error("pageSize outside supported range");
      }

      if (domain != null && !["support", "chat", "voice"].includes(domain)) {
        throw new Error("invalid domain; expected one of ['support', 'chat', 'voice']");
      }

      return await client.post(
        `/api_v2/tars/api/rpt-dashboard/${pathSegment(domain)}/${pathSegment(tabKey)}`,
        {
          body: {
            startDate: startDate,
            endDate: endDate,
            teamIdList: teamIdList,
            agentIdList: agentIdList,
            brandIdList: brandIdList,
            brandNameList: brandNameList,
            channelList: channelList,
            platformList: platformList,
            channelIdList: channelIdList,
            supportEmailIdList: supportEmailIdList,
            ticketTypeIdList: ticketTypeIdList,
            livechatTypeList: livechatTypeList,
            phoneNumberList: phoneNumberList,
            voiceDirectionList: voiceDirectionList,
            voiceTypeList: voiceTypeList,
            completionStatusList: completionStatusList,
            initiatorTypeList: initiatorTypeList,
            assignmentStatusList: assignmentStatusList,
            slaPolicyIdList: slaPolicyIdList,
            slaMetricTypeList: slaMetricTypeList,
            groupField: groupField,
            dimensionType: dimensionType,
            dateGrain: dateGrain,
            pageNum: pageNum,
            pageSize: pageSize,
            keyword: keyword,
            sortField: sortField,
            sortOrder: sortOrder,
          },
        },
      );
    },
  },
  "reports-chart": {
    parameters: {
      startDate: { type: "string" },
      endDate: { type: "string" },
      teamIdList: { type: "integer[]" },
      agentIdList: { type: "integer[]" },
      brandIdList: { type: "integer[]" },
      brandNameList: { type: "string[]" },
      channelList: { type: "string[]" },
      platformList: { type: "string[]" },
      channelIdList: { type: "integer[]" },
      supportEmailIdList: { type: "integer[]" },
      ticketTypeIdList: { type: "integer[]" },
      livechatTypeList: { type: "string[]" },
      phoneNumberList: { type: "string[]" },
      voiceDirectionList: { type: "string[]" },
      voiceTypeList: { type: "string[]" },
      completionStatusList: { type: "string[]" },
      initiatorTypeList: { type: "string[]" },
      assignmentStatusList: { type: "string[]" },
      slaPolicyIdList: { type: "integer[]" },
      slaMetricTypeList: { type: "string[]" },
      groupField: { type: "string" },
      dimensionType: { type: "string" },
      dateGrain: { type: "string" },
      pageNum: { type: "integer" },
      pageSize: { type: "integer" },
      keyword: { type: "string" },
      sortField: { type: "string" },
      sortOrder: { type: "string" },
      domain: { type: "string", required: true },
      tabKey: { type: "string", required: true },
      chartKey: { type: "string", required: true },
    },
    async run(client, params) {
      const {
        startDate,
        endDate,
        teamIdList,
        agentIdList,
        brandIdList,
        brandNameList,
        channelList,
        platformList,
        channelIdList,
        supportEmailIdList,
        ticketTypeIdList,
        livechatTypeList,
        phoneNumberList,
        voiceDirectionList,
        voiceTypeList,
        completionStatusList,
        initiatorTypeList,
        assignmentStatusList,
        slaPolicyIdList,
        slaMetricTypeList,
        groupField,
        dimensionType,
        dateGrain,
        pageNum,
        pageSize,
        keyword,
        sortField,
        sortOrder,
        domain,
        tabKey,
        chartKey,
      } = params;

      if (pageNum != null && pageNum < 1) {
        throw new Error("pageNum outside supported range");
      }

      if (pageSize != null && (pageSize < 1 || pageSize > 100)) {
        throw new Error("pageSize outside supported range");
      }

      if (domain != null && !["support", "chat", "voice"].includes(domain)) {
        throw new Error("invalid domain; expected one of ['support', 'chat', 'voice']");
      }

      return await client.post(
        `/api_v2/tars/api/rpt-dashboard/${pathSegment(domain)}/${pathSegment(tabKey)}/charts/${pathSegment(chartKey)}`,
        {
          body: {
            startDate: startDate,
            endDate: endDate,
            teamIdList: teamIdList,
            agentIdList: agentIdList,
            brandIdList: brandIdList,
            brandNameList: brandNameList,
            channelList: channelList,
            platformList: platformList,
            channelIdList: channelIdList,
            supportEmailIdList: supportEmailIdList,
            ticketTypeIdList: ticketTypeIdList,
            livechatTypeList: livechatTypeList,
            phoneNumberList: phoneNumberList,
            voiceDirectionList: voiceDirectionList,
            voiceTypeList: voiceTypeList,
            completionStatusList: completionStatusList,
            initiatorTypeList: initiatorTypeList,
            assignmentStatusList: assignmentStatusList,
            slaPolicyIdList: slaPolicyIdList,
            slaMetricTypeList: slaMetricTypeList,
            groupField: groupField,
            dimensionType: dimensionType,
            dateGrain: dateGrain,
            pageNum: pageNum,
            pageSize: pageSize,
            keyword: keyword,
            sortField: sortField,
            sortOrder: sortOrder,
          },
        },
      );
    },
  },
  "reports-table": {
    parameters: {
      startDate: { type: "string" },
      endDate: { type: "string" },
      teamIdList: { type: "integer[]" },
      agentIdList: { type: "integer[]" },
      brandIdList: { type: "integer[]" },
      brandNameList: { type: "string[]" },
      channelList: { type: "string[]" },
      platformList: { type: "string[]" },
      channelIdList: { type: "integer[]" },
      supportEmailIdList: { type: "integer[]" },
      ticketTypeIdList: { type: "integer[]" },
      livechatTypeList: { type: "string[]" },
      phoneNumberList: { type: "string[]" },
      voiceDirectionList: { type: "string[]" },
      voiceTypeList: { type: "string[]" },
      completionStatusList: { type: "string[]" },
      initiatorTypeList: { type: "string[]" },
      assignmentStatusList: { type: "string[]" },
      slaPolicyIdList: { type: "integer[]" },
      slaMetricTypeList: { type: "string[]" },
      groupField: { type: "string" },
      dimensionType: { type: "string" },
      dateGrain: { type: "string" },
      pageNum: { type: "integer", default: 1 },
      pageSize: { type: "integer", default: 50 },
      keyword: { type: "string" },
      sortField: { type: "string" },
      sortOrder: { type: "string" },
      domain: { type: "string", required: true },
      tabKey: { type: "string", required: true },
      tableKey: { type: "string", required: true },
    },
    async run(client, params) {
      const {
        startDate,
        endDate,
        teamIdList,
        agentIdList,
        brandIdList,
        brandNameList,
        channelList,
        platformList,
        channelIdList,
        supportEmailIdList,
        ticketTypeIdList,
        livechatTypeList,
        phoneNumberList,
        voiceDirectionList,
        voiceTypeList,
        completionStatusList,
        initiatorTypeList,
        assignmentStatusList,
        slaPolicyIdList,
        slaMetricTypeList,
        groupField,
        dimensionType,
        dateGrain,
        pageNum,
        pageSize,
        keyword,
        sortField,
        sortOrder,
        domain,
        tabKey,
        tableKey,
      } = params;

      if (pageNum != null && pageNum < 1) {
        throw new Error("pageNum outside supported range");
      }

      if (pageSize != null && (pageSize < 1 || pageSize > 100)) {
        throw new Error("pageSize outside supported range");
      }

      if (domain != null && !["support", "chat", "voice"].includes(domain)) {
        throw new Error("invalid domain; expected one of ['support', 'chat', 'voice']");
      }

      return await client.pages(
        "POST",
        `/api_v2/tars/api/rpt-dashboard/${pathSegment(domain)}/${pathSegment(tabKey)}/tables/${pathSegment(tableKey)}`,
        {
          body: {
            startDate: startDate,
            endDate: endDate,
            teamIdList: teamIdList,
            agentIdList: agentIdList,
            brandIdList: brandIdList,
            brandNameList: brandNameList,
            channelList: channelList,
            platformList: platformList,
            channelIdList: channelIdList,
            supportEmailIdList: supportEmailIdList,
            ticketTypeIdList: ticketTypeIdList,
            livechatTypeList: livechatTypeList,
            phoneNumberList: phoneNumberList,
            voiceDirectionList: voiceDirectionList,
            voiceTypeList: voiceTypeList,
            completionStatusList: completionStatusList,
            initiatorTypeList: initiatorTypeList,
            assignmentStatusList: assignmentStatusList,
            slaPolicyIdList: slaPolicyIdList,
            slaMetricTypeList: slaMetricTypeList,
            groupField: groupField,
            dimensionType: dimensionType,
            dateGrain: dateGrain,
            pageNum: pageNum,
            pageSize: pageSize,
            keyword: keyword,
            sortField: sortField,
            sortOrder: sortOrder,
          },
          items_key: "rows",
          page_key: "pageNum",
          size_key: "pageSize",
        },
      );
    },
  },
  "admin-views-public": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/ticket/view/public/list");
    },
  },
  "admin-views-private": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/ticket/view/private/list-v2");
    },
  },
  "admin-view": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return await client.get(`/api_v2/tars/api/ticket/view/${pathSegment(id)}`);
    },
  },
  "admin-automation-list": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/automation/list");
    },
  },
  "admin-automation-get": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return await client.get(`/api_v2/tars/api/automation/${pathSegment(id)}`);
    },
  },
  "admin-automation-task": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/automation/task");
    },
  },
  "admin-triggers": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/trigger/rules");
    },
  },
  "admin-trigger-categories": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/trigger/categories");
    },
  },
  "admin-trigger-channel-options": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/trigger/condition-options/channel-types");
    },
  },
  "admin-sla-policies": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/sla/policies");
    },
  },
  "admin-sla-metadata": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/sla/metadata");
    },
  },
  "admin-queues": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/routing/queues");
    },
  },
  "admin-queue": {
    parameters: { queueId: { type: "string", required: true } },
    async run(client, params) {
      const { queueId } = params;

      return await client.get(`/api_v2/tars/api/routing/queues/${pathSegment(queueId)}`);
    },
  },
  "admin-queue-channels": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/routing/queues/options/channels");
    },
  },
  "admin-queue-languages": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/routing/queues/options/languages");
    },
  },
  "admin-routing-activation": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/routing/activation");
    },
  },
  "admin-teams": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/teams");
    },
  },
  "admin-calendars": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/routing/business-calendars");
    },
  },
  "admin-calendar": {
    parameters: { calendarId: { type: "string", required: true } },
    async run(client, params) {
      const { calendarId } = params;

      return await client.get(
        `/api_v2/tars/api/routing/business-calendars/${pathSegment(calendarId)}`,
      );
    },
  },
  "admin-capacity": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/routing/capacity-rules");
    },
  },
  "admin-capacity-get": {
    parameters: { ruleId: { type: "string", required: true } },
    async run(client, params) {
      const { ruleId } = params;

      return await client.get(`/api_v2/tars/api/routing/capacity-rules/${pathSegment(ruleId)}`);
    },
  },
  "admin-capacity-default": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/routing/capacity-rules/default");
    },
  },
  "admin-members": {
    parameters: { content: { type: "string" } },
    async run(client, params) {
      const { content } = params;

      return await client.get("/api_v2/tars/api/user/management_list", {
        params: { content: content },
      });
    },
  },
  "admin-member": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return await client.get(`/api_v2/tars/api/user/${pathSegment(id)}/getUserInfo`);
    },
  },
  "admin-roles": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/role/list");
    },
  },
  "admin-role": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return await client.get(`/api_v2/tars/api/role/${pathSegment(id)}`);
    },
  },
  "admin-role-members": {
    parameters: { id: { type: "string", required: true } },
    async run(client, params) {
      const { id } = params;

      return await client.get(`/api_v2/tars/api/role/${pathSegment(id)}/user_list`);
    },
  },
  "admin-permissions": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/permission/list");
    },
  },
  "admin-my-permissions": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/user/permission_list");
    },
  },
  "admin-fields": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/custom/field/list");
    },
  },
  "admin-ai-tag-policy": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/tags/policy");
    },
  },
  "admin-inactivity": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/ticket-timer/customer-inactivity-close");
    },
  },
  "admin-satisfaction-templates": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/satisfaction/templates");
    },
  },
  "admin-satisfaction-versions": {
    parameters: { templateId: { type: "integer" }, language: { type: "string" } },
    async run(client, params) {
      const { templateId, language } = params;

      return await client.get("/api_v2/tars/api/satisfaction/templates/versions", {
        params: { templateId: templateId, language: language },
      });
    },
  },
  "admin-satisfaction-auto-send": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/satisfaction/templates/auto-send");
    },
  },
  "admin-outreach-plans": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/tars/api/outreach/directed/plans");
    },
  },
  "admin-outreach-runs": {
    parameters: {
      planId: { type: "string", required: true },
      page: { type: "integer", default: 1 },
      pageSize: { type: "integer", default: 50 },
    },
    async run(client, params) {
      const { planId, page, pageSize } = params;

      if (page != null && page < 1) {
        throw new Error("page outside supported range");
      }

      if (pageSize != null && pageSize < 1) {
        throw new Error("pageSize outside supported range");
      }
      return await client.pages(
        "GET",
        `/api_v2/tars/api/outreach/directed/plans/${pathSegment(planId)}/runs/page`,
        {
          params: { page: page, pageSize: pageSize },
          items_key: "list",
          page_key: "page",
          size_key: "pageSize",
        },
      );
    },
  },
  "admin-outreach-run": {
    parameters: {
      planId: { type: "string", required: true },
      runId: { type: "string", required: true },
    },
    async run(client, params) {
      const { planId, runId } = params;

      return await client.get(
        `/api_v2/tars/api/outreach/directed/plans/${pathSegment(planId)}/runs/${pathSegment(runId)}`,
      );
    },
  },
  "admin-outreach-import": {
    parameters: { importId: { type: "string", required: true } },
    async run(client, params) {
      const { importId } = params;

      return await client.get(
        `/api_v2/tars/api/outreach/directed/imports/${pathSegment(importId)}`,
      );
    },
  },
  "admin-outreach-attempts": {
    parameters: { recipientId: { type: "string", required: true } },
    async run(client, params) {
      const { recipientId } = params;

      return await client.get(
        `/api_v2/tars/api/outreach/directed/recipients/${pathSegment(recipientId)}/attempts`,
      );
    },
  },
  "admin-trigger-executions": {
    parameters: {
      before: { type: "integer" },
      limit: { type: "integer", default: 20 },
      ticketId: { type: "string", required: true },
    },
    async run(client, params) {
      const { before, limit, ticketId } = params;

      if (limit != null && (limit < 1 || limit > 50)) {
        throw new Error("limit outside supported range");
      }

      return await client.pages(
        "GET",
        `/api_v2/tars/api/trigger/tickets/${pathSegment(ticketId)}/executions`,
        {
          params: { before: before, limit: limit },
          items_key: "items",
          page_key: "before",
          size_key: "limit",
          cursor: true,
        },
      );
    },
  },
  "admin-trigger-preview": {
    parameters: {
      ticketNumber: { type: "string", required: true },
      id: { type: "string", required: true },
    },
    async run(client, params) {
      const { ticketNumber, id } = params;

      return await client.post(`/api_v2/tars/api/trigger/rules/${pathSegment(id)}/preview`, {
        body: { ticketNumber: ticketNumber },
      });
    },
  },
  "admin-settings-list": {
    parameters: { types: { type: "array", required: true } },
    async run(client, params) {
      const { types } = params;

      return await client.post("/api_v2/tars/api/system/setting/list", { body: types });
    },
  },
  "admin-toolbar-configs": {
    parameters: {},
    async run(client, params) {
      return sanitize(await client.get("/api_v2/tars/api/toolbar-extension/configs"));
    },
  },
  "admin-whatsapp-accounts": {
    parameters: {},
    async run(client, params) {
      return await client.get("/api_v2/intelli/whatsapp/templates/wabaAccounts");
    },
  },
  "admin-whatsapp-templates": {
    parameters: {
      wabaId: { type: "string", required: true },
      page: { type: "integer", default: 1 },
      limit: { type: "integer", default: 50 },
      includeTotal: { type: "boolean", default: true },
      name: { type: "string" },
    },
    async run(client, params) {
      const { wabaId, page, limit, includeTotal, name } = params;

      if (page != null && page < 1) {
        throw new Error("page outside supported range");
      }

      if (limit != null && (limit < 1 || limit > 100)) {
        throw new Error("limit outside supported range");
      }

      return await client.pages("GET", "/api_v2/intelli/whatsapp/templates/list", {
        params: {
          wabaId: wabaId,
          page: page,
          limit: limit,
          includeTotal: includeTotal,
          name: name,
        },
        items_key: "data",
        page_key: "page",
        size_key: "limit",
      });
    },
  },
  "admin-whatsapp-template": {
    parameters: {
      name: { type: "string", required: true },
      language: { type: "string", required: true },
      wabaId: { type: "string", required: true },
    },
    async run(client, params) {
      const { name, language, wabaId } = params;

      return await client.get(`/api_v2/intelli/whatsapp/templates/${pathSegment(wabaId)}/get`, {
        params: { name: name, language: language },
      });
    },
  },
  "admin-templates": {
    parameters: { page: { type: "integer", default: 1 }, size: { type: "integer", default: 20 } },
    async run(client, params) {
      const { page, size } = params;

      if (page != null && page < 1) {
        throw new Error("page outside supported range");
      }

      if (size != null && size < 1) {
        throw new Error("size outside supported range");
      }
      return await client.pages("GET", "/api_v2/tars/api/templates/list", {
        params: { page: page, size: size },
        items_key: "list",
        page_key: "page",
        size_key: "size",
        total_key: "totalCount",
      });
    },
  },
  "admin-outreach-recipients": {
    parameters: {
      planId: { type: "string", required: true },
      runId: { type: "string", required: true },
      page: { type: "integer", default: 1 },
      pageSize: { type: "integer", default: 100 },
    },
    async run(client, params) {
      const { planId, runId, page, pageSize } = params;

      if (page != null && page < 1) {
        throw new Error("page outside supported range");
      }

      if (pageSize != null && pageSize < 1) {
        throw new Error("pageSize outside supported range");
      }
      return await client.pages(
        "GET",
        `/api_v2/tars/api/outreach/directed/plans/${pathSegment(planId)}/runs/${pathSegment(runId)}/recipients`,
        {
          params: { page: page, pageSize: pageSize },
          items_key: "$",
          page_key: "page",
          size_key: "pageSize",
        },
      );
    },
  },
  "admin-outreach-import-rows": {
    parameters: {
      importId: { type: "string", required: true },
      afterRow: { type: "integer" },
      limit: { type: "integer", default: 100 },
      validOnly: { type: "boolean", default: false },
    },
    async run(client, params) {
      const { importId, afterRow, limit, validOnly } = params;

      if (afterRow != null && afterRow < 0) {
        throw new Error("afterRow outside supported range");
      }

      if (limit != null && limit < 1) {
        throw new Error("limit outside supported range");
      }

      return await client.get(
        `/api_v2/tars/api/outreach/directed/imports/${pathSegment(importId)}/rows`,
        { params: { afterRow: afterRow, limit: limit, validOnly: validOnly } },
      );
    },
  },
  "customers-export": {
    parameters: {
      keyword: { type: "string" },
      personaId: { type: "integer" },
      emotionType: { type: "string" },
      sortOrder: { type: "string", default: "desc" },
    },
    async run(client, params) {
      const { keyword, personaId, emotionType, sortOrder } = params;

      if (personaId != null && personaId < 1) {
        throw new Error("personaId outside supported range");
      }

      if (sortOrder != null && !["asc", "desc"].includes(sortOrder)) {
        throw new Error("invalid sortOrder; expected one of ['asc', 'desc']");
      }
      return await client.download("/api_v2/tars/api/customer/plg/export", {
        params: {
          keyword: keyword,
          personaId: personaId,
          emotionType: emotionType,
          sortOrder: sortOrder,
        },
      });
    },
  },
  "customers-import-template": {
    parameters: {},
    async run(client, params) {
      return await client.download("/api_v2/tars/api/customer/plg/import/template", { params: {} });
    },
  },
  "admin-trigger-intent-options": {
    parameters: { projectId: { type: "integer", required: true } },
    async run(client, params) {
      const { projectId } = params;

      return await client.get("/api_v2/tars/api/trigger/condition-options/ai-intents", {
        params: { projectId: projectId },
      });
    },
  },
  "admin-sla-preview": {
    parameters: {
      ticketId: { type: "integer" },
      priority: { type: "string" },
      ticket: { type: "object", required: true },
    },
    async run(client, params) {
      const { ticketId, priority, ticket } = params;

      return await client.post("/api_v2/tars/api/sla/preview-match", {
        body: { ticketId: ticketId, priority: priority, ticket: ticket },
      });
    },
  },
};
