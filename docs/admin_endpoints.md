# Agent Orchestration Admin API — Markdown Documentation

## Overview

This document describes the **Admin API** endpoints for managing agents, orchestration sessions, invocations, events, artifacts, and ADK sessions.

**Base URL**

```text
http://10.73.83.83:8000
```

**API Prefix**

```text
/admin
```

**Authentication**

All endpoints require the following header:

```http
x-admin-token: super-secret
```

If the token is missing or invalid, the API returns:

```json
{
  "detail": "Unauthorized"
}
```

***

# Common Response Models

## Pagination Response

Paginated APIs return data in the following format:

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5
  }
}
```

## Error Response

```json
{
  "detail": "Error message"
}
```

## Sensitive Data Redaction

The backend redacts sensitive fields from response payloads.

Examples of redacted keys:

```text
access_token
refresh_token
id_token
authorization
token
api_key
secret
client_secret
```

Redacted values are returned as:

```text
***REDACTED***
```

***

# 1. Dashboard Summary

## Get Dashboard Summary

```http
GET /admin/dashboard/summary
```

Returns aggregate counts for agents, orchestration sessions, invocations, artifacts, users, and ADK sessions.

### Headers

```http
x-admin-token: <SECRET_KEY>
```

### Response `200`

```json
{
  "agents": {
    "total": 10,
    "active": 8,
    "inactive": 2,
    "healthy": 7,
    "unhealthy": 3
  },
  "orchestration_sessions": {
    "total": 120,
    "running": 4,
    "completed": 110,
    "failed": 6
  },
  "invocations": {
    "total": 350,
    "total_tokens": 145000
  },
  "artifacts": {
    "total": 45
  },
  "users": {
    "total": 20
  },
  "adk_sessions": {
    "total": 80
  }
}
```

### Error Responses

| Status | Description  |
| ------ | ------------ |
| `403`  | Unauthorized |

***

# 2. Agents

## List Agents

```http
GET /admin/agents
```

Returns a paginated list of registered agents.

### Query Parameters

| Name         |    Type | Required | Default | Description               |
| ------------ | ------: | -------: | ------: | ------------------------- |
| `search`     |  string |       No |  `null` | Search by agent name      |
| `is_active`  | boolean |       No |  `null` | Filter by active status   |
| `is_healthy` | boolean |       No |  `null` | Filter by health status   |
| `page`       | integer |       No |     `1` | Page number               |
| `page_size`  | integer |       No |    `20` | Items per page, max `100` |

### Example Request

```http
GET /admin/agents?search=research&page=1&page_size=20
```

### Response `200`

```json
{
  "items": [
    {
      "id": 1,
      "name": "research_agent",
      "host": "localhost",
      "port": 8081,
      "is_active": true,
      "is_healthy": true,
      "created_at": "2026-05-08T09:00:00Z",
      "last_health_check": "2026-05-08T09:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1
  }
}
```

***

## Get Agent Detail

```http
GET /admin/agents/{agent_name}
```

Returns details, stats, and recent invocations for a specific agent.

### Path Parameters

| Name         |   Type | Required | Description |
| ------------ | -----: | -------: | ----------- |
| `agent_name` | string |      Yes | Agent name  |

### Example Request

```http
GET /admin/agents/research_agent
```

### Response `200`

```json
{
  "agent": {
    "id": 1,
    "name": "research_agent",
    "host": "localhost",
    "port": 8081,
    "is_active": true,
    "is_healthy": true,
    "created_at": "2026-05-08T09:00:00Z",
    "last_health_check": "2026-05-08T09:30:00Z",
    "agent_card": {
      "name": "research_agent",
      "description": "Research agent"
    }
  },
  "stats": {
    "total_invocations": 25,
    "completed": 22,
    "failed": 2,
    "running": 1,
    "total_tokens": 56000
  },
  "recent_invocations": [
    {
      "id": 101,
      "orchestration_session_id": 12,
      "agent_session_id": "agent-session-123",
      "step_order": 1,
      "status": "completed",
      "started_at": "2026-05-08T09:00:00Z",
      "completed_at": "2026-05-08T09:00:12Z",
      "total_tokens": 1200,
      "duration_seconds": 12.0
    }
  ]
}
```

### Error Responses

| Status | Description     |
| ------ | --------------- |
| `404`  | Agent not found |

***

## Register Agent

```http
POST /admin/agents
```

Creates a new agent.

If `agent_card` is not provided, the backend attempts to fetch it from:

```text
http://{host}:{port}/.well-known/agent-card.json
```

### Request Body

```json
{
  "name": "research_agent",
  "host": "localhost",
  "port": 8081,
  "is_active": true,
  "is_healthy": true,
  "agent_card": {
    "name": "research_agent",
    "description": "Research agent"
  }
}
```

### Required Fields

| Field        |    Type | Required | Description              |
| ------------ | ------: | -------: | ------------------------ |
| `name`       |  string |      Yes | Agent name               |
| `host`       |  string |      Yes | Agent host               |
| `port`       | integer |      Yes | Agent port               |
| `is_active`  | boolean |       No | Active status            |
| `is_healthy` | boolean |       No | Health status            |
| `agent_card` |  object |       No | Optional agent card JSON |

### Response `201`

```json
{
  "message": "Agent created successfully",
  "agent": {
    "id": 1,
    "name": "research_agent",
    "host": "localhost",
    "port": 8081,
    "is_active": true,
    "is_healthy": true,
    "created_at": "2026-05-08T09:00:00Z",
    "last_health_check": "2026-05-08T09:00:00Z",
    "agent_card": {
      "name": "research_agent",
      "description": "Research agent"
    }
  }
}
```

### Error Responses

| Status | Description                                                                       |
| ------ | --------------------------------------------------------------------------------- |
| `400`  | Invalid request, agent card timeout, failed fetch, invalid JSON, or name mismatch |
| `409`  | Agent already exists                                                              |

***

## Update Agent

```http
PATCH /admin/agents/{agent_name}
```

Updates one or more fields for a registered agent.

### Path Parameters

| Name         |   Type | Required | Description |
| ------------ | -----: | -------: | ----------- |
| `agent_name` | string |      Yes | Agent name  |

### Request Body

All fields are optional.

```json
{
  "host": "localhost",
  "port": 8082,
  "is_active": true,
  "is_healthy": false,
  "agent_card": {
    "name": "research_agent",
    "description": "Updated research agent"
  }
}
```

### Response `200`

```json
{
  "message": "Agent updated successfully",
  "agent": {
    "id": 1,
    "name": "research_agent",
    "host": "localhost",
    "port": 8082,
    "is_active": true,
    "is_healthy": false,
    "created_at": "2026-05-08T09:00:00Z",
    "last_health_check": "2026-05-08T09:30:00Z",
    "agent_card": {
      "name": "research_agent",
      "description": "Updated research agent"
    }
  }
}
```

### Error Responses

| Status | Description     |
| ------ | --------------- |
| `404`  | Agent not found |

***

## Delete Agent Permanently

```http
DELETE /admin/agents/{agent_name}
```

Permanently removes the agent from the database and from the runtime `root_agent.sub_agents` list.

### Path Parameters

| Name         |   Type | Required | Description |
| ------------ | -----: | -------: | ----------- |
| `agent_name` | string |      Yes | Agent name  |

### Response `200`

```json
{
  "message": "Agent 'research_agent' deleted permanently"
}
```

### Error Responses

| Status | Description     |
| ------ | --------------- |
| `404`  | Agent not found |

***

# 3. Orchestration Sessions

## List Orchestration Sessions

```http
GET /admin/orchestration-sessions
```

Returns paginated orchestration sessions with invocation count, token usage, artifact count, and duration.

### Query Parameters

| Name         |    Type | Required | Default | Description               |
| ------------ | ------: | -------: | ------: | ------------------------- |
| `status`     |  string |       No |  `null` | Filter by status          |
| `user_id`    |  string |       No |  `null` | Search by user ID         |
| `session_id` |  string |       No |  `null` | Search by session ID      |
| `page`       | integer |       No |     `1` | Page number               |
| `page_size`  | integer |       No |    `20` | Items per page, max `100` |

### Example Request

```http
GET /admin/orchestration-sessions?status=completed&page=1&page_size=20
```

### Response `200`

```json
{
  "items": [
    {
      "id": 12,
      "session_id": "session-abc",
      "user_id": "user@example.com",
      "status": "completed",
      "created_at": "2026-05-08T09:00:00Z",
      "completed_at": "2026-05-08T09:02:00Z",
      "invocation_count": 3,
      "artifact_count": 1,
      "total_tokens": 4500,
      "duration_seconds": 120.0
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1
  }
}
```

***

## Get Orchestration Session Detail

```http
GET /admin/orchestration-sessions/{session_db_id}
```

Returns orchestration session details including invocations, dependencies, events, and artifacts.

### Path Parameters

| Name            |    Type | Required | Description                              |
| --------------- | ------: | -------: | ---------------------------------------- |
| `session_db_id` | integer |      Yes | Database ID of the orchestration session |

### Response `200`

```json
{
  "session": {
    "id": 12,
    "session_id": "session-abc",
    "user_id": "user@example.com",
    "status": "completed",
    "created_at": "2026-05-08T09:00:00Z",
    "completed_at": "2026-05-08T09:02:00Z",
    "duration_seconds": 120.0
  },
  "invocations": [
    {
      "id": 101,
      "agent_name": "research_agent",
      "agent_session_id": "agent-session-123",
      "step_order": 1,
      "status": "completed",
      "input_payload": {
        "query": "Find latest sales report"
      },
      "output_payload": {
        "result": "Report found"
      },
      "started_at": "2026-05-08T09:00:00Z",
      "completed_at": "2026-05-08T09:00:30Z",
      "input_tokens": 300,
      "output_tokens": 700,
      "total_tokens": 1000,
      "duration_seconds": 30.0
    }
  ],
  "dependencies": [
    {
      "id": 1,
      "parent_invocation_id": 101,
      "child_invocation_id": 102,
      "dependency_type": "sequential",
      "created_at": "2026-05-08T09:00:01Z"
    }
  ],
  "events": [
    {
      "id": 1,
      "invocation_id": 101,
      "event_type": "tool_call",
      "payload": {
        "tool": "search"
      },
      "created_at": "2026-05-08T09:00:05Z"
    }
  ],
  "artifacts": [
    {
      "id": 1,
      "invocation_id": 101,
      "file_id": "file-123",
      "filename": "report.pdf",
      "url": "https://example.com/report.pdf",
      "path": "/files/report.pdf",
      "tenant_id": "tenant-1",
      "user_id": "user@example.com",
      "session_id": "session-abc",
      "mime_type": "application/pdf",
      "file_size": 204800,
      "created_at": "2026-05-08T09:01:00Z"
    }
  ]
}
```

### Error Responses

| Status | Description                     |
| ------ | ------------------------------- |
| `404`  | Orchestration session not found |

***

# 4. Invocations

## List Invocations

```http
GET /admin/invocations
```

Returns paginated agent invocations.

### Query Parameters

| Name                       |    Type | Required | Default | Description                                 |
| -------------------------- | ------: | -------: | ------: | ------------------------------------------- |
| `agent_name`               |  string |       No |  `null` | Filter by agent name                        |
| `status`                   |  string |       No |  `null` | Filter by invocation status                 |
| `orchestration_session_id` | integer |       No |  `null` | Filter by orchestration session database ID |
| `page`                     | integer |       No |     `1` | Page number                                 |
| `page_size`                | integer |       No |    `20` | Items per page, max `100`                   |

### Example Request

```http
GET /admin/invocations?agent_name=research&status=completed&page=1&page_size=20
```

### Response `200`

```json
{
  "items": [
    {
      "id": 101,
      "orchestration_session_id": 12,
      "agent_name": "research_agent",
      "agent_session_id": "agent-session-123",
      "step_order": 1,
      "status": "completed",
      "started_at": "2026-05-08T09:00:00Z",
      "completed_at": "2026-05-08T09:00:30Z",
      "input_tokens": 300,
      "output_tokens": 700,
      "total_tokens": 1000,
      "duration_seconds": 30.0
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1
  }
}
```

***

## Get Invocation Detail

```http
GET /admin/invocations/{invocation_id}
```

Returns invocation details including events, artifacts, and dependencies.

### Path Parameters

| Name            |    Type | Required | Description   |
| --------------- | ------: | -------: | ------------- |
| `invocation_id` | integer |      Yes | Invocation ID |

### Response `200`

```json
{
  "invocation": {
    "id": 101,
    "orchestration_session_id": 12,
    "agent_name": "research_agent",
    "agent_session_id": "agent-session-123",
    "step_order": 1,
    "status": "completed",
    "input_payload": {
      "query": "Find latest sales report"
    },
    "output_payload": {
      "result": "Report found"
    },
    "started_at": "2026-05-08T09:00:00Z",
    "completed_at": "2026-05-08T09:00:30Z",
    "input_tokens": 300,
    "output_tokens": 700,
    "total_tokens": 1000,
    "duration_seconds": 30.0
  },
  "events": [
    {
      "id": 1,
      "event_type": "tool_call",
      "payload": {
        "tool": "search"
      },
      "created_at": "2026-05-08T09:00:05Z"
    }
  ],
  "artifacts": [
    {
      "id": 1,
      "file_id": "file-123",
      "filename": "report.pdf",
      "url": "https://example.com/report.pdf",
      "path": "/files/report.pdf",
      "tenant_id": "tenant-1",
      "user_id": "user@example.com",
      "session_id": "session-abc",
      "mime_type": "application/pdf",
      "file_size": 204800,
      "created_at": "2026-05-08T09:01:00Z"
    }
  ],
  "dependencies": [
    {
      "id": 1,
      "parent_invocation_id": 101,
      "child_invocation_id": 102,
      "dependency_type": "sequential",
      "created_at": "2026-05-08T09:00:01Z"
    }
  ]
}
```

### Error Responses

| Status | Description          |
| ------ | -------------------- |
| `404`  | Invocation not found |

***

# 5. Agent Events

## List Agent Events

```http
GET /admin/agent-events
```

Returns paginated agent events, optionally filtered by invocation, event type, or agent name.

### Query Parameters

| Name            |    Type | Required | Default | Description               |
| --------------- | ------: | -------: | ------: | ------------------------- |
| `invocation_id` | integer |       No |  `null` | Filter by invocation ID   |
| `event_type`    |  string |       No |  `null` | Filter by event type      |
| `agent_name`    |  string |       No |  `null` | Filter by agent name      |
| `page`          | integer |       No |     `1` | Page number               |
| `page_size`     | integer |       No |    `50` | Items per page, max `100` |

### Example Request

```http
GET /admin/agent-events?event_type=tool_call&page=1&page_size=50
```

### Response `200`

```json
{
  "items": [
    {
      "id": 1,
      "invocation_id": 101,
      "event_type": "tool_call",
      "payload": {
        "tool": "search"
      },
      "created_at": "2026-05-08T09:00:05Z",
      "agent_name": "research_agent"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total": 1,
    "total_pages": 1
  }
}
```

***

# 6. Artifacts

## List Artifacts

```http
GET /admin/artifacts
```

Returns paginated artifacts with optional filtering.

### Query Parameters

| Name            |    Type | Required | Default | Description               |
| --------------- | ------: | -------: | ------: | ------------------------- |
| `tenant_id`     |  string |       No |  `null` | Filter by tenant ID       |
| `user_id`       |  string |       No |  `null` | Search by user ID         |
| `session_id`    |  string |       No |  `null` | Search by session ID      |
| `invocation_id` | integer |       No |  `null` | Filter by invocation ID   |
| `mime_type`     |  string |       No |  `null` | Filter by MIME type       |
| `page`          | integer |       No |     `1` | Page number               |
| `page_size`     | integer |       No |    `20` | Items per page, max `100` |

### Example Request

```http
GET /admin/artifacts?mime_type=application/pdf&page=1&page_size=20
```

### Response `200`

```json
{
  "items": [
    {
      "id": 1,
      "invocation_id": 101,
      "file_id": "file-123",
      "filename": "report.pdf",
      "url": "https://example.com/report.pdf",
      "path": "/files/report.pdf",
      "tenant_id": "tenant-1",
      "user_id": "user@example.com",
      "session_id": "session-abc",
      "mime_type": "application/pdf",
      "file_size": 204800,
      "created_at": "2026-05-08T09:01:00Z",
      "agent_name": "research_agent"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1
  }
}
```

***

# 7. ADK Sessions

## List ADK Sessions

```http
GET /admin/adk-sessions
```

Returns paginated ADK sessions.

### Query Parameters

| Name         |    Type | Required | Default | Description               |
| ------------ | ------: | -------: | ------: | ------------------------- |
| `app_name`   |  string |       No |  `null` | Filter by app name        |
| `user_id`    |  string |       No |  `null` | Search by user ID         |
| `session_id` |  string |       No |  `null` | Search by session ID      |
| `page`       | integer |       No |     `1` | Page number               |
| `page_size`  | integer |       No |    `20` | Items per page, max `100` |

### Example Request

```http
GET /admin/adk-sessions?app_name=my_app&page=1&page_size=20
```

### Response `200`

```json
{
  "items": [
    {
      "app_name": "my_app",
      "user_id": "user@example.com",
      "session_id": "adk-session-123",
      "create_time": "2026-05-08T09:00:00Z",
      "update_time": "2026-05-08T09:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1
  }
}
```

***

## Get ADK Session Detail

```http
GET /admin/adk-sessions/{app_name}/{user_id}/{session_id}
```

Returns ADK session state and recent ADK events.

### Path Parameters

| Name         |   Type | Required | Description    |
| ------------ | -----: | -------: | -------------- |
| `app_name`   | string |      Yes | ADK app name   |
| `user_id`    | string |      Yes | User ID        |
| `session_id` | string |      Yes | ADK session ID |

### Query Parameters

| Name                  |    Type | Required | Default | Description                                  |
| --------------------- | ------: | -------: | ------: | -------------------------------------------- |
| `recent_events_limit` | integer |       No |    `50` | Number of recent events to return, max `200` |

### Example Request

```http
GET /admin/adk-sessions/my_app/user@example.com/adk-session-123?recent_events_limit=50
```

### Response `200`

```json
{
  "session": {
    "app_name": "my_app",
    "user_id": "user@example.com",
    "session_id": "adk-session-123",
    "state": {
      "current_step": "completed"
    },
    "create_time": "2026-05-08T09:00:00Z",
    "update_time": "2026-05-08T09:30:00Z"
  },
  "recent_events": [
    {
      "id": "event-123",
      "app_name": "my_app",
      "user_id": "user@example.com",
      "session_id": "adk-session-123",
      "invocation_id": "invocation-123",
      "timestamp": "2026-05-08T09:20:00Z",
      "event_data": {
        "type": "message",
        "content": "Event payload"
      }
    }
  ]
}
```

### Error Responses

| Status | Description           |
| ------ | --------------------- |
| `404`  | ADK session not found |

***

# Endpoint Summary

| Method   | Endpoint                                                | Description                      |
| -------- | ------------------------------------------------------- | -------------------------------- |
| `GET`    | `/admin/dashboard/summary`                              | Get dashboard summary            |
| `GET`    | `/admin/agents`                                         | List agents                      |
| `POST`   | `/admin/agents`                                         | Register agent                   |
| `GET`    | `/admin/agents/{agent_name}`                            | Get agent detail                 |
| `PATCH`  | `/admin/agents/{agent_name}`                            | Update agent                     |
| `DELETE` | `/admin/agents/{agent_name}`                            | Delete agent permanently         |
| `GET`    | `/admin/orchestration-sessions`                         | List orchestration sessions      |
| `GET`    | `/admin/orchestration-sessions/{session_db_id}`         | Get orchestration session detail |
| `GET`    | `/admin/invocations`                                    | List invocations                 |
| `GET`    | `/admin/invocations/{invocation_id}`                    | Get invocation detail            |
| `GET`    | `/admin/agent-events`                                   | List agent events                |
| `GET`    | `/admin/artifacts`                                      | List artifacts                   |
| `GET`    | `/admin/adk-sessions`                                   | List ADK sessions                |
| `GET`    | `/admin/adk-sessions/{app_name}/{user_id}/{session_id}` | Get ADK session detail           |

***

# Front-End Notes

## Required Header

Every request must include:

```http
x-admin-token: <SECRET_KEY>
```

## Pagination

Use `page` and `page_size` for list endpoints.

Example:

```http
GET /admin/agents?page=1&page_size=20
```

## Date Fields

Date/time fields are returned as ISO-style datetime values, for example:

```text
2026-05-08T09:00:00Z
```

## Nullable Fields

Some fields may be `null`, especially:

```text
completed_at
duration_seconds
agent_session_id
input_payload
output_payload
file_id
url
path
mime_type
file_size
```

## Recommended Front-End Sections

Your admin UI can map these APIs into the following pages:

1.  **Dashboard**
    *   Uses `/admin/dashboard/summary`

2.  **Agents**
    *   Uses `/admin/agents`
    *   Uses `/admin/agents/{agent_name}`

3.  **Orchestration Sessions**
    *   Uses `/admin/orchestration-sessions`
    *   Uses `/admin/orchestration-sessions/{session_db_id}`

4.  **Invocations**
    *   Uses `/admin/invocations`
    *   Uses `/admin/invocations/{invocation_id}`

5.  **Agent Events**
    *   Uses `/admin/agent-events`

6.  **Artifacts**
    *   Uses `/admin/artifacts`

7.  **ADK Sessions**
    *   Uses `/admin/adk-sessions`
    *   Uses `/admin/adk-sessions/{app_name}/{user_id}/{session_id}`
