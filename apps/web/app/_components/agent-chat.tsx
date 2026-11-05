"use client";

import { activeTurn, failure, interaction, turns } from "eve/events";
import { useEveAgent, type EveMessage } from "eve/react";
import { AlertCircleIcon, AlertTriangleIcon, BrainIcon, SquareIcon } from "lucide-react";
import { Fragment, useRef, useState } from "react";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
  ConversationTopFade,
} from "@/components/ai-elements/conversation";
import { Message, MessageContent } from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputButton,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";
import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { cn } from "@/lib/utils";

import { AgentMessage } from "./agent-message";
import { unverifiedNumbers } from "./number-check";
import type { AgentAnswer } from "./agent-message";

type EveAgent = ReturnType<typeof useEveAgent>;

/** The session id in a `/s/[sessionId]` URL, when rendering in the browser. */
function getSessionIdFromLocation(): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  const match = /^\/s\/([^/]+)$/.exec(window.location.pathname);
  return match?.[1] === undefined ? undefined : decodeURIComponent(match[1]);
}

/** Whether to show the thinking indicator, and the empty assistant message it replaces. */
interface PendingAssistant {
  readonly hiddenMessageId: string | undefined;
  readonly showThinking: boolean;
}

/** Display state derived from the agent on each render. */
interface ChatView {
  readonly activeSessionId: string | undefined;
  /** A running or paused turn that the Stop control can cancel. */
  readonly canCancel: boolean;
  readonly errorMessage: string | undefined;
  /** The empty assistant message hidden while the thinking indicator stands in for it. */
  readonly hiddenMessageId: string | undefined;
  readonly isBusy: boolean;
  readonly isResuming: boolean;
  readonly showConversationLayout: boolean;
  readonly showPendingThinking: boolean;
}

/**
 * The web chat: a centered composer for a new chat, then a conversation view
 * whose URL (`/s/[sessionId]`) resumes the durable session on reload.
 *
 * @param props - The component props.
 * @returns The chat page.
 */
export function AgentChat({
  sessionId: sessionIdProp,
  sessionless = false,
}: {
  /** Session to resume, from the `/s/[sessionId]` route. */
  readonly sessionId?: string;
  /** Show the conversation layout before the first message (`/s`). */
  readonly sessionless?: boolean;
}) {
  // Read once: the store only uses its initial session config. Falling back to the
  // URL covers Back navigation to a `/s/<id>` entry whose page tree is `/` or `/s`.
  const [sessionId] = useState(() => sessionIdProp ?? getSessionIdFromLocation());
  const [actionError, setActionError] = useState<string>();
  const [hasInputText, setHasInputText] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const agent = useEveAgent({
    initialSession:
      sessionId === undefined ? undefined : { sessionId, streamIndex: 0 },
    resume: sessionId !== undefined,
    onSessionChange(session) {
      if (session === undefined) {
        return;
      }
      // Fires on every stream event; only touch history when the URL changes.
      const path = `/s/${encodeURIComponent(session.sessionId)}`;
      if (window.location.pathname !== path) {
        window.history.replaceState(null, "", path);
      }
    },
  });

  const view = getChatView(agent, {
    actionError,
    sessionId,
    sessionless,
  });

  const requestCancellation = async () => {
    setActionError(undefined);
    try {
      await agent.cancel();
    } catch (error) {
      setActionError(
        error instanceof Error
          ? error.message
          : "Unable to cancel the response."
      );
    }
  };

  const sendText = async (value: string) => {
    const text = value.trim();
    if (text.length === 0 || view.isResuming) {
      return;
    }

    setActionError(undefined);
    try {
      await agent.send(
        text,
        view.isBusy ? { turnPolicy: "steer" as const } : undefined
      );
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Unable to send your message."
      );
      // PromptInput clears the box on submit; put the text back for a retry
      // unless the visitor has started typing something else.
      const textarea = textareaRef.current;
      if (textarea !== null && textarea.value === "") {
        textarea.value = value;
        setHasInputText(text.length > 0);
      }
    }
  };

  const handleSubmit = async (message: PromptInputMessage) => {
    if (message.text.trim().length > 0) {
      setHasInputText(false);
    }
    await sendText(message.text);
  };

  const composer = (
    <PromptInput maxFiles={0} onSubmit={handleSubmit}>
      <PromptInputTextarea
        disabled={view.isResuming}
        onChange={(event) => {
          setHasInputText(event.currentTarget.value.trim().length > 0);
        }}
        placeholder="Ask about deals, products, companies…"
        ref={textareaRef}
      />
      <ComposerAction
        hasInputText={hasInputText}
        isBusy={view.canCancel}
        isResuming={view.isResuming}
        onCancel={() => {
          void requestCancellation();
        }}
      />
    </PromptInput>
  );

  return (
    <main className="bg-background text-foreground relative flex h-[calc(100dvh-var(--header-height))] flex-col overflow-hidden">
      {view.showConversationLayout ? (
        <ChatConversation
          agent={agent}
          isInitialSession={sessionId !== undefined}
          onAnswers={async (answers) => {
            setActionError(undefined);
            try {
              await agent.respond(answers);
            } catch (error) {
              setActionError(
                error instanceof Error
                  ? error.message
                  : "Unable to send your response."
              );
              // Rethrow so the question or approval re-enables for a retry.
              throw error;
            }
          }}
          view={view}
        />
      ) : null}
      <div
        className={cn(
          "mx-auto w-full px-4 sm:px-6",
          view.showConversationLayout
            ? "from-background via-background absolute bottom-0 left-1/2 z-20 max-w-3xl -translate-x-1/2 bg-gradient-to-t to-transparent pt-4 pb-6"
            : "flex max-w-2xl flex-1 flex-col items-center justify-center"
        )}
      >
        <div className="w-full">{composer}</div>
      </div>
    </main>
  );
}

/**
 * Derives what the chat should show from the agent's state.
 *
 * @param agent - The `useEveAgent` result.
 * @param options - Chat state held outside the agent.
 * @returns The derived {@link ChatView}.
 */
function getChatView(
  agent: EveAgent,
  {
    actionError,
    sessionId,
    sessionless,
  }: {
    /** The last failed send, cancellation, or response, if any. */
    readonly actionError: string | undefined;
    /** Session being resumed, if any. */
    readonly sessionId: string | undefined;
    /** Whether to show the conversation layout before any messages. */
    readonly sessionless: boolean;
  }
): ChatView {
  const isBusy = agent.status === "busy";
  const isResuming = agent.status === "resuming";
  const canCancel = activeTurn(agent.view) !== undefined;
  const pending = getPendingAssistant(agent, isBusy);
  const turnFailure =
    isBusy || isResuming ? undefined : getLatestTurnFailure(agent.view);
  const errorMessage = actionError ?? agent.error?.message ?? turnFailure;
  const hasConversationContent =
    sessionless || agent.messages.length > 0 || errorMessage !== undefined;

  return {
    activeSessionId: sessionId ?? agent.session?.sessionId,
    canCancel,
    errorMessage,
    hiddenMessageId: pending.hiddenMessageId,
    isBusy,
    isResuming,
    showConversationLayout: isResuming || hasConversationContent,
    showPendingThinking: pending.showThinking,
  };
}

/**
 * Decides whether to show the thinking indicator, and which empty assistant
 * message (one with no visible response, tool, or interaction parts) it replaces.
 *
 * @param agent - The `useEveAgent` result.
 * @param isBusy - Whether a turn is submitted or streaming.
 * @returns Whether to show the indicator, and the message ID it hides.
 */
function getPendingAssistant(
  agent: EveAgent,
  isBusy: boolean
): PendingAssistant {
  const lastMessage = agent.messages.at(-1);
  if (!isBusy) {
    return { hiddenMessageId: undefined, showThinking: false };
  }
  if (lastMessage?.role !== "assistant") {
    return { hiddenMessageId: undefined, showThinking: true };
  }
  const isEmptyShell = lastMessage.parts.every(
    (part) =>
      part.type !== "text" &&
      part.type !== "reasoning" &&
      part.type !== "tool" &&
      part.type !== "interaction"
  );
  return {
    hiddenMessageId: isEmptyShell ? lastMessage.id : undefined,
    showThinking: isEmptyShell,
  };
}

/**
 * The scrolling message list, with the thinking indicator and any error.
 *
 * @param props - The component props.
 * @returns The conversation.
 */
function ChatConversation({
  agent,
  isInitialSession,
  onAnswers,
  view,
}: {
  /** The `useEveAgent` result. */
  readonly agent: EveAgent;
  /** Whether the page opened on an existing session. */
  readonly isInitialSession: boolean;
  /** Submits answers to questions and approvals. */
  readonly onAnswers: (
    responses: readonly AgentAnswer[]
  ) => Promise<void>;
  /** The derived {@link ChatView}. */
  readonly view: ChatView;
}) {
  const { messages } = agent;
  const canRespond = (interactionId: string) =>
    !view.isResuming && interaction(agent.view, interactionId)?.status === "open";
  const scrollKey =
    messages.length > 0 && view.activeSessionId !== undefined
      ? `eve:web-chat-scroll:${view.activeSessionId}`
      : undefined;

  return (
    <Conversation
      className="min-h-0 flex-1"
      initial={isInitialSession ? false : undefined}
      resize={view.activeSessionId === undefined ? "smooth" : "instant"}
      scrollRestorationKey={scrollKey}
    >
      <ConversationTopFade />
      <ConversationContent className="mx-auto w-full max-w-3xl gap-6 px-4 pt-8 pb-36 sm:px-6">
        {messages.map((message, index) => {
          if (message.id === view.hiddenMessageId) {
            return null;
          }
          const isStreaming =
            agent.status === "busy" && message.id === messages.at(-1)?.id;
          return (
            <Fragment key={message.id}>
              <AgentMessage
                canRespond={canRespond}
                isStreaming={isStreaming}
                message={message}
                onAnswers={onAnswers}
              />
              {isStreaming ? null : (
                <UnverifiedNumbers
                  numbers={unverifiedNumbers(messages, index)}
                  question={messages[index - 1]}
                />
              )}
            </Fragment>
          );
        })}
        {view.showPendingThinking ? <PendingThinking /> : null}
        {view.errorMessage === undefined ? null : (
          <ErrorMessage message={view.errorMessage} />
        )}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  );
}

/** The warning's wording, in the language of the question it answers. */
function unverifiedText(question: EveMessage | undefined, numbers: string): string {
  const text = question?.parts.flatMap((part) => (part.type === "text" ? [part.text] : [])).join(" ") ?? "";
  if (/[А-Яа-яЁё]/u.test(text)) {
    return `Проверьте: ${numbers} нет в результатах запросов. Агент мог посчитать это сам.`;
  }
  if (/[‘’ʻ]|\b(yil|yilda|qancha|nechta|qaysi|bo.lgan|aylanma)/iu.test(text)) {
    return `Tekshiring: ${numbers} so‘rov natijalarida yo‘q. Agent buni o‘zi hisoblagan bo‘lishi mumkin.`;
  }
  return `Check this: ${numbers} isn't in any query result. The agent may have worked it out itself.`;
}

/** Flags numbers the agent stated without a query behind them, so a slip is never silent. */
function UnverifiedNumbers({
  numbers,
  question,
}: {
  readonly numbers: readonly string[];
  readonly question: EveMessage | undefined;
}) {
  if (numbers.length === 0) {
    return null;
  }
  return (
    <p
      className="text-muted-foreground bg-card flex w-fit max-w-full items-start gap-2 rounded-lg border px-3 py-2 text-xs"
      role="note"
    >
      <AlertTriangleIcon aria-hidden="true" className="mt-px size-3.5 shrink-0" />
      <span>{unverifiedText(question, numbers.join(", "))}</span>
    </p>
  );
}

/**
 * The composer's action button: send, or stop while a turn runs and the composer is empty.
 *
 * @param props - The component props.
 * @returns The send or stop button.
 */
function ComposerAction({
  hasInputText,
  isBusy,
  isResuming,
  onCancel,
}: {
  /** Whether the textarea has text. */
  readonly hasInputText: boolean;
  /** Whether a turn is running. */
  readonly isBusy: boolean;
  /** Whether the session is still catching up. */
  readonly isResuming: boolean;
  /** Cancels the running turn. */
  readonly onCancel: () => void;
}) {
  const canSubmit = hasInputText;

  if (!isBusy || canSubmit) {
    return <PromptInputSubmit disabled={isResuming || !canSubmit} />;
  }

  return (
    <PromptInputButton
      aria-label="Stop"
      className="absolute right-2.5 bottom-2.5"
      onClick={onCancel}
      variant="outline"
    >
      <SquareIcon className="size-3 fill-current" />
    </PromptInputButton>
  );
}

/**
 * An assistant-style message reporting a failed request or turn.
 *
 * @param props - The component props.
 * @returns The error message.
 */
function ErrorMessage({
  message,
}: {
  /** The error to show. */
  readonly message: string;
}) {
  return (
    <Message className="max-w-full" from="assistant">
      <MessageContent>
        <div
          className="border-destructive/30 bg-destructive/5 flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-sm"
          role="alert"
        >
          <AlertCircleIcon className="text-destructive mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">Request failed</p>
            <p className="text-muted-foreground mt-0.5">{message}</p>
          </div>
        </div>
      </MessageContent>
    </Message>
  );
}

/**
 * Placeholder shown until the assistant's first output arrives.
 *
 * @returns The thinking indicator.
 */
function PendingThinking() {
  return (
    <Message aria-live="polite" from="assistant">
      <MessageContent>
        <div className="text-muted-foreground mb-4 flex w-full items-center gap-2 text-sm">
          <BrainIcon className="size-4" />
          <Shimmer duration={1}>Thinking</Shimmer>
        </div>
      </MessageContent>
    </Message>
  );
}

/**
 * Finds the latest turn failure, ignoring failures a later turn or message superseded.
 *
 * @param view - The agent's committed session view.
 * @returns A user-facing failure message, or `undefined` when the latest turn did not fail.
 */
function getLatestTurnFailure(view: EveAgent["view"]): string | undefined {
  const latestTurn = turns(view).at(-1);
  const turnFailure = failure(view, latestTurn?.turnId);
  if (turnFailure !== undefined) {
    return turnFailure.code === "MODEL_CALL_FAILED"
      ? "The model is temporarily unavailable. Please try again."
      : turnFailure.message;
  }
  return undefined;
}
