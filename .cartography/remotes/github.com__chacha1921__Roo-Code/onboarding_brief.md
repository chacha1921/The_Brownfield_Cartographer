# onboarding_brief

This brief summarizes the semantic synthesis for a new forward-deployed engineer joining the codebase.
Citations below are propagated directly from Semanticist day-one answers to keep downstream references stable for AI-assisted onboarding.

## What business capability does this codebase primarily support?
This codebase primarily supports an AI-powered code assistant that integrates with a development environment, enabling users to interact conversationally with AI models. It facilitates the automation of coding tasks, execution of commands, modification of files, and management of development workflows directly within the environment.

Evidence:
- src/core/webview/ClineProvider.ts:L101-L130 via llm-inference
- src/core/task/Task.ts:L151-L180 via llm-inference
- src/shared/tools.ts:L76-L105 via llm-inference
- src/core/assistant-message/presentAssistantMessage.ts:L26-L55 via llm-inference

## Which modules and workflows should a new engineer read first to understand the system's critical path?
To grasp the system's critical path, a new engineer should begin by examining these core modules and their interactions:
1.  `src/core/webview/ClineProvider.ts`: This is the central entry point for the VSCode extension, managing the webview, task stack, and overall state. It's where new tasks are created and managed, initiating the user's interaction flow.
2.  `src/core/task/Task.ts`: This class represents an individual AI task, handling the conversation history, API calls, tool execution, and checkpointing. It encapsulates the core logic for an ongoing AI interaction.
3.  `src/core/assistant-message/presentAssistantMessage.ts`: This function is crucial for understanding how the AI's streamed responses are parsed, displayed, and how tool calls are initiated and approved, acting as the primary dispatcher for AI output.
4.  `src/shared/tools.ts`: This file defines the comprehensive set of capabilities (tools) the AI can invoke, such as `read_file`, `write_to_file`, and `execute_command`. Familiarity with these definitions is essential for understanding the AI's operational scope.
5.  `src/api/providers/anthropic.ts`: As a concrete example of an AI provider, this file illustrates how messages are formatted for the LLM, how streaming responses are handled, and how token usage is calculated. It provides insight into the direct interaction with the AI model.

Evidence:
- src/core/webview/ClineProvider.ts:L2901-L2930 via llm-inference
- src/core/task/Task.ts:L301-L330 via llm-inference
- src/core/assistant-message/presentAssistantMessage.ts:L276-L305 via llm-inference
- src/shared/tools.ts:L251-L280 via llm-inference
- src/api/providers/anthropic.ts:L26-L55 via llm-inference

## Where are the highest-risk change surfaces, and why?
The highest-risk change surfaces are concentrated in core modules that manage AI interaction, tool execution, and overall extension state, primarily due to their high change velocity and architectural centrality.
1.  `src/shared/tools.ts`: This file defines fundamental types and interfaces for all AI tools. Any modification here has a cascading effect across all tool implementations and AI model integrations, making it a high-impact change surface. Its high change count (7) underscores its frequent evolution.
2.  `src/core/assistant-message/presentAssistantMessage.ts`: This module is the central dispatcher for AI responses, responsible for parsing text, handling tool calls, and managing user approvals. Changes to this logic can directly impact the AI's ability to communicate and act, and its high change count (7) indicates it's a frequent point of modification.
3.  `src/core/webview/ClineProvider.ts`: As the primary VSCode extension provider, this file orchestrates the entire user experience, including task lifecycle, state persistence, and webview communication. Its architectural centrality means changes can affect UI responsiveness, task stability, and overall extension functionality. The high change count (7) reflects its dynamic nature.
4.  `src/core/task/Task.ts`: This class embodies the core state machine for an AI task, managing conversation history, API interactions, and tool execution. Alterations here can introduce subtle bugs in the AI's reasoning or execution flow, making it a critical and high-velocity (7 changes) component.
5.  `src/api/providers/anthropic.ts`: This file represents a direct interface with a major AI model. Changes to its `createMessage` method or model parameter handling can significantly alter AI behavior, response quality, and cost. Its high change count (7) suggests ongoing adjustments to optimize AI interaction.

Evidence:
- src/shared/tools.ts:L76-L105 via llm-inference
- src/core/assistant-message/presentAssistantMessage.ts:L26-L55 via llm-inference
- src/core/webview/ClineProvider.ts:L101-L130 via llm-inference
- src/core/task/Task.ts:L151-L180 via llm-inference
- src/api/providers/anthropic.ts:L26-L55 via llm-inference

## How does data enter, move through, and exit the system?
Data enters the system through user interactions and cloud synchronization, undergoes AI processing and tool execution, and exits via the user interface, file system modifications, and telemetry.

**Entry Points:**
*   **User Input:** Users initiate tasks via the webview chat or VSCode commands. The `ClineProvider`'s `createTask` method captures initial prompts and images, while `handleCodeAction` and `handleTerminalAction` process context from the editor or terminal.
*   **Cloud Synchronization:** Organization settings and provider profiles are fetched from a cloud service, influencing the system's configuration.

**Processing Stages:**
*   **Task Initialization:** A `Task` instance is created, encapsulating the conversation. It loads historical messages and sets up the API configuration.
*   **Prompt Construction:** The `Task` aggregates user messages, system prompts, and tool definitions into a structured format for the AI model.
*   **AI API Interaction:** The `Task` sends the formatted messages to the configured AI provider (e.g., Anthropic). The provider handles the streaming response, yielding chunks of text or tool calls.
*   **Assistant Message Interpretation:** The `presentAssistantMessage` function processes the AI's streamed output. It displays text directly to the user and, crucially, parses and dispatches tool calls for execution.
*   **Tool Execution:** Based on AI instructions, specific tool handlers (e.g., `writeToFileTool`, `executeCommandTool`) interact with the local environment, performing file operations, running commands, or accessing resources. User approval may be required.
*   **State Persistence:** Throughout the process, the `Task` and `ClineProvider` persist conversation history, tool usage, and task metadata to local storage.

**Output Artifacts/Exit Points:**
*   **User Interface:** Processed AI text, tool outputs, and task status updates are rendered in the webview.
*   **File System & Terminal:** Tools directly modify files in the workspace or execute commands, producing terminal output.
*   **Telemetry:** Anonymous usage data, including tool usage and API costs, is captured and sent to a telemetry service.
*   **Task History:** Tasks are saved as history items, allowing users to resume or review past interactions.

Evidence:
- src/core/webview/ClineProvider.ts:L701-L730 via llm-inference
- src/core/webview/ClineProvider.ts:L326-L355 via llm-inference
- src/core/task/Task.ts:L301-L330 via llm-inference
- src/api/providers/anthropic.ts:L26-L55 via llm-inference
- src/core/assistant-message/presentAssistantMessage.ts:L676-L705 via llm-inference
- src/core/webview/ClineProvider.ts:L1101-L1130 via llm-inference
- src/shared/tools.ts:L76-L105 via llm-inference
- src/core/task/Task.ts:L51-L80 via llm-inference
- src/core/webview/ClineProvider.ts:L1701-L1730 via llm-inference

## What domain architecture map best explains how responsibilities are split across the codebase?
The codebase exhibits a clear separation of concerns, best explained by a layered architecture with distinct domains for user interaction, core AI logic, external integrations, and data management.

1.  **Presentation Layer (User Interface & VSCode Integration):** This layer manages the visual interface (webview), handles user input, and integrates with VSCode's extension APIs for commands, panels, and workspace events. It serves as the primary interface for the user.
    *   **Key Modules:** `src/core/webview/ClineProvider.ts` (manages webview lifecycle, state, and communication), `webview-ui/` (React components for the chat interface, settings, etc.), `src/extension.ts` (VSCode extension activation and command registration).
2.  **Application Layer (Core AI Task Orchestration):** This layer orchestrates the end-to-end lifecycle of an AI-driven task. This includes managing the conversation flow, coordinating AI model calls, dispatching tool executions, and handling task-specific state and checkpoints.
    *   **Key Modules:** `src/core/task/Task.ts` (the state machine for an individual AI task, managing history, API calls, and tool execution), `src/core/assistant-message/presentAssistantMessage.ts` (interprets AI responses, dispatches tool calls, and updates the UI).
3.  **Domain Layer (AI Model & Tooling Abstractions):** This layer defines the core business logic related to AI model interaction and the capabilities (tools) the AI can use. It provides abstractions for different AI providers and a standardized way to define and execute tools.
    *   **Key Modules:** `src/api/providers/` (abstracts different LLM APIs, e.g., `anthropic.ts`), `src/shared/tools.ts` (defines the universal tool interface and parameters), `src/core/tools/` (concrete implementations of native tools).
4.  **Infrastructure Layer (External Integrations & Persistence):** This layer handles interactions with external systems and persistent storage. This includes file system operations, terminal command execution, cloud services, and local state persistence.
    *   **Key Modules:** `src/services/mcp/McpHub.ts` (managing external MCP servers), `src/services/checkpoints/ShadowCheckpointService.ts` (workspace state management), `src/core/task-persistence/` (saving/loading task messages and API history), `src/utils/fs.ts` (file system utilities).

Evidence:
- src/core/webview/ClineProvider.ts:L101-L130 via llm-inference
- src/core/task/Task.ts:L151-L180 via llm-inference
- src/core/assistant-message/presentAssistantMessage.ts:L26-L55 via llm-inference
- src/api/providers/anthropic.ts:L26-L55 via llm-inference
- src/shared/tools.ts:L76-L105 via llm-inference
- src/core/webview/ClineProvider.ts:L1626-L1655 via llm-inference
- src/core/task/Task.ts:L51-L80 via llm-inference
