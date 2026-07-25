/**
 * AIChatPage - Conversational AI assistant interface.
 * Users can ask natural language questions about their financial data.
 * Handles: successful responses with numbers/time ranges, timeout with retry,
 * insufficient data with days remaining, out-of-scope with example questions,
 * and rate limiting.
 * Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
 */
import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { useLocale } from '../contexts/LocaleContext';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/** Timeout for AI query requests (10 seconds per Req 11.4) */
const QUERY_TIMEOUT_MS = 10_000;

type MessageRole = 'user' | 'assistant' | 'error';

interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  errorType?: 'timeout' | 'out_of_scope' | 'insufficient_data' | 'rate_limit' | 'generic';
  exampleQuestions?: string[];
  retryQuestion?: string;
}

export default function AIChatPage() {
  const { locale } = useLocale();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  function generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  }

  function addUserMessage(question: string): void {
    const msg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: question,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, msg]);
  }

  function addAssistantMessage(content: string): void {
    const msg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      content,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, msg]);
  }

  function addErrorMessage(
    content: string,
    errorType: ChatMessage['errorType'],
    options?: { exampleQuestions?: string[]; retryQuestion?: string }
  ): void {
    const msg: ChatMessage = {
      id: generateId(),
      role: 'error',
      content,
      timestamp: new Date(),
      errorType,
      exampleQuestions: options?.exampleQuestions,
      retryQuestion: options?.retryQuestion,
    };
    setMessages((prev) => [...prev, msg]);
  }

  function parseExampleQuestions(message: string): string[] {
    // Try to extract example questions from the response message
    const examples: string[] = [];
    const lines = message.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      // Match lines that look like example questions (start with - or • or number.)
      if (/^[-•]\s+/.test(trimmed)) {
        examples.push(trimmed.replace(/^[-•]\s+/, ''));
      } else if (/^\d+[.)]\s+/.test(trimmed)) {
        examples.push(trimmed.replace(/^\d+[.)]\s+/, ''));
      }
    }
    return examples;
  }

  async function sendQuery(question: string): Promise<void> {
    setIsLoading(true);

    try {
      const response = await axios.post(
        `${API_BASE}/api/ai/query`,
        { question },
        { timeout: QUERY_TIMEOUT_MS }
      );

      const { success, message, error_type } = response.data;

      if (success) {
        // Req 11.1, 11.2: Successful answer with specific numbers and time range
        addAssistantMessage(message);
      } else if (error_type === 'out_of_scope') {
        // Req 11.6: Out-of-scope with guidance and example questions
        const examples = parseExampleQuestions(message);
        addErrorMessage(message, 'out_of_scope', { exampleQuestions: examples });
      } else if (error_type === 'insufficient_data') {
        // Req 11.3: States what data is missing with days remaining
        addErrorMessage(message, 'insufficient_data');
      } else {
        // Generic error from API
        addErrorMessage(message || 'Something went wrong. Please try again.', 'generic');
      }
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.code === 'ECONNABORTED' || !error.response) {
          // Req 11.5: Timeout — show "assistant unavailable" with retry button
          addErrorMessage(
            'The assistant is currently unavailable. Please try again.',
            'timeout',
            { retryQuestion: question }
          );
        } else if (error.response?.status === 503) {
          // Service unavailable — same as timeout behavior
          addErrorMessage(
            'The assistant is currently unavailable. Please try again.',
            'timeout',
            { retryQuestion: question }
          );
        } else if (error.response?.status === 429) {
          // Rate limited
          const waitMessage =
            error.response.data?.message ||
            "You've reached the query limit. Please wait a moment before trying again.";
          addErrorMessage(waitMessage, 'rate_limit');
        } else {
          addErrorMessage(
            'Something went wrong. Please try again.',
            'generic',
            { retryQuestion: question }
          );
        }
      } else {
        addErrorMessage(
          'Network error. Please check your connection and try again.',
          'generic',
          { retryQuestion: question }
        );
      }
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent): void {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    addUserMessage(trimmed);
    setInput('');
    sendQuery(trimmed);
  }

  function handleRetry(question: string): void {
    if (isLoading) return;
    addUserMessage(question);
    sendQuery(question);
  }

  function handleExampleClick(question: string): void {
    if (isLoading) return;
    setInput(question);
    inputRef.current?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  if (!locale) {
    return (
      <div className="page page-ai-chat">
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="page page-ai-chat" style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <h1 style={styles.heading}>AI Assistant</h1>
        <p style={styles.subtitle}>Ask questions about your finances</p>
      </div>

      {/* Messages area */}
      <div style={styles.messagesContainer} role="log" aria-live="polite" aria-label="Chat messages">
        {messages.length === 0 && (
          <div style={styles.emptyState}>
            <p style={styles.emptyTitle}>No conversations yet</p>
            <p style={styles.emptyHint}>
              Try asking something like:
            </p>
            <div style={styles.exampleList}>
              <button
                type="button"
                style={styles.exampleButton}
                onClick={() => handleExampleClick('How much did I spend on food this week?')}
              >
                How much did I spend on food this week?
              </button>
              <button
                type="button"
                style={styles.exampleButton}
                onClick={() => handleExampleClick('What are my top spending categories this month?')}
              >
                What are my top spending categories this month?
              </button>
              <button
                type="button"
                style={styles.exampleButton}
                onClick={() => handleExampleClick('How does my spending compare to last month?')}
              >
                How does my spending compare to last month?
              </button>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} style={styles.messageWrapper}>
            {msg.role === 'user' && (
              <div style={styles.userMessage}>
                <p style={styles.userMessageText}>{msg.content}</p>
              </div>
            )}

            {msg.role === 'assistant' && (
              <div style={styles.assistantMessage}>
                <p style={styles.assistantMessageText}>{msg.content}</p>
              </div>
            )}

            {msg.role === 'error' && (
              <div
                style={{
                  ...styles.errorMessage,
                  ...(msg.errorType === 'timeout' ? styles.errorTimeout : {}),
                  ...(msg.errorType === 'out_of_scope' ? styles.errorOutOfScope : {}),
                  ...(msg.errorType === 'insufficient_data' ? styles.errorInsufficientData : {}),
                  ...(msg.errorType === 'rate_limit' ? styles.errorRateLimit : {}),
                }}
                role="alert"
              >
                <p style={styles.errorMessageText}>{msg.content}</p>

                {/* Retry button for timeout errors (Req 11.5) */}
                {msg.errorType === 'timeout' && msg.retryQuestion && (
                  <button
                    type="button"
                    style={styles.retryButton}
                    onClick={() => handleRetry(msg.retryQuestion!)}
                    disabled={isLoading}
                    aria-label="Retry query"
                  >
                    Retry
                  </button>
                )}

                {/* Generic error retry */}
                {msg.errorType === 'generic' && msg.retryQuestion && (
                  <button
                    type="button"
                    style={styles.retryButton}
                    onClick={() => handleRetry(msg.retryQuestion!)}
                    disabled={isLoading}
                    aria-label="Retry query"
                  >
                    Retry
                  </button>
                )}

                {/* Example questions for out-of-scope (Req 11.6) */}
                {msg.errorType === 'out_of_scope' && msg.exampleQuestions && msg.exampleQuestions.length > 0 && (
                  <div style={styles.examplesSection}>
                    <p style={styles.examplesLabel}>Try asking:</p>
                    <div style={styles.exampleList}>
                      {msg.exampleQuestions.map((q, i) => (
                        <button
                          key={i}
                          type="button"
                          style={styles.exampleButton}
                          onClick={() => handleExampleClick(q)}
                          disabled={isLoading}
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Loading indicator */}
        {isLoading && (
          <div style={styles.loadingWrapper}>
            <div style={styles.loadingDots} aria-label="Thinking">
              <span style={styles.dot}>●</span>
              <span style={{ ...styles.dot, animationDelay: '0.2s' }}>●</span>
              <span style={{ ...styles.dot, animationDelay: '0.4s' }}>●</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <form onSubmit={handleSubmit} style={styles.inputArea}>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your finances..."
          style={styles.input}
          disabled={isLoading}
          aria-label="Type your question"
          autoComplete="off"
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          style={{
            ...styles.sendButton,
            ...(isLoading || !input.trim() ? styles.sendButtonDisabled : {}),
          }}
          aria-label="Send question"
        >
          Send
        </button>
      </form>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    maxHeight: 'calc(100vh - 80px)',
    overflow: 'hidden',
  },
  header: {
    padding: '0 0 0.75rem 0',
    borderBottom: '1px solid #f3f4f6',
    flexShrink: 0,
  },
  heading: {
    fontSize: '1.5rem',
    fontWeight: '700',
    marginBottom: '0.125rem',
  },
  subtitle: {
    fontSize: '0.85rem',
    color: '#6b7280',
    margin: 0,
  },
  messagesContainer: {
    flex: 1,
    overflowY: 'auto',
    padding: '1rem 0',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
    padding: '2rem 1rem',
    flex: 1,
  },
  emptyTitle: {
    fontSize: '1rem',
    fontWeight: '600',
    color: '#6b7280',
    marginBottom: '0.5rem',
  },
  emptyHint: {
    fontSize: '0.85rem',
    color: '#9ca3af',
    marginBottom: '1rem',
  },
  messageWrapper: {
    display: 'flex',
    flexDirection: 'column',
  },
  userMessage: {
    alignSelf: 'flex-end',
    maxWidth: '80%',
    padding: '0.625rem 0.875rem',
    borderRadius: '12px 12px 2px 12px',
    background: '#2563eb',
    color: '#fff',
  },
  userMessageText: {
    fontSize: '0.9rem',
    lineHeight: '1.4',
    margin: 0,
    whiteSpace: 'pre-wrap',
  },
  assistantMessage: {
    alignSelf: 'flex-start',
    maxWidth: '85%',
    padding: '0.625rem 0.875rem',
    borderRadius: '12px 12px 12px 2px',
    background: '#f3f4f6',
    color: '#1f2937',
  },
  assistantMessageText: {
    fontSize: '0.9rem',
    lineHeight: '1.5',
    margin: 0,
    whiteSpace: 'pre-wrap',
  },
  errorMessage: {
    alignSelf: 'flex-start',
    maxWidth: '85%',
    padding: '0.75rem 0.875rem',
    borderRadius: '12px 12px 12px 2px',
    background: '#fef2f2',
    border: '1px solid #fecaca',
  },
  errorTimeout: {
    background: '#fef3c7',
    border: '1px solid #fde68a',
  },
  errorOutOfScope: {
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
  },
  errorInsufficientData: {
    background: '#f5f3ff',
    border: '1px solid #ddd6fe',
  },
  errorRateLimit: {
    background: '#fff7ed',
    border: '1px solid #fed7aa',
  },
  errorMessageText: {
    fontSize: '0.9rem',
    lineHeight: '1.4',
    margin: 0,
    color: '#374151',
    whiteSpace: 'pre-wrap',
  },
  retryButton: {
    marginTop: '0.5rem',
    padding: '0.375rem 0.875rem',
    fontSize: '0.85rem',
    fontWeight: '600',
    borderRadius: '6px',
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    cursor: 'pointer',
  },
  examplesSection: {
    marginTop: '0.5rem',
    paddingTop: '0.5rem',
    borderTop: '1px solid #ddd6fe',
  },
  examplesLabel: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#6b7280',
    marginBottom: '0.375rem',
  },
  exampleList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
  },
  exampleButton: {
    padding: '0.5rem 0.75rem',
    fontSize: '0.8rem',
    borderRadius: '8px',
    border: '1px solid #e0e0e0',
    background: '#fff',
    color: '#2563eb',
    cursor: 'pointer',
    textAlign: 'left',
    transition: 'background 0.2s',
  },
  loadingWrapper: {
    alignSelf: 'flex-start',
    padding: '0.625rem 0.875rem',
    borderRadius: '12px 12px 12px 2px',
    background: '#f3f4f6',
  },
  loadingDots: {
    display: 'flex',
    gap: '0.25rem',
    alignItems: 'center',
  },
  dot: {
    fontSize: '0.6rem',
    color: '#6b7280',
    animation: 'pulse 1.2s infinite',
  },
  inputArea: {
    display: 'flex',
    gap: '0.5rem',
    padding: '0.75rem 0 0 0',
    borderTop: '1px solid #f3f4f6',
    flexShrink: 0,
  },
  input: {
    flex: 1,
    padding: '0.625rem 0.75rem',
    fontSize: '0.95rem',
    borderRadius: '8px',
    border: '2px solid #e0e0e0',
    background: '#fff',
    outline: 'none',
    transition: 'border-color 0.2s',
  },
  sendButton: {
    padding: '0.625rem 1rem',
    fontSize: '0.9rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
    transition: 'background 0.2s',
    whiteSpace: 'nowrap',
  },
  sendButtonDisabled: {
    background: '#93c5fd',
    cursor: 'not-allowed',
  },
};
