# Implementation Plan: Daily Money Tracker

## Overview

This plan implements the Daily Money Tracker PWA from project scaffolding through full feature delivery. The backend uses Python (FastAPI + SQLAlchemy + MySQL), the frontend uses React + TypeScript, and the system integrates an LLM API for AI assistant features. Implementation proceeds in layers: shared foundations first, then core transaction logging, habit/streak mechanics, budgets, insights, AI integration, and finally PWA offline/push capabilities.

## Tasks

- [x] 1. Project scaffolding and shared foundations
  - [x] 1.1 Set up backend project structure
    - Initialize Python project with `pyproject.toml`
    - Create directory structure: `backend/app/{api,models,services,schemas,utils,jobs,tests}`
    - Install dependencies: fastapi, uvicorn, sqlalchemy, alembic, apscheduler, pydantic, hypothesis, pywebpush, python-jose
    - Configure FastAPI app with CORS middleware
    - Configure SQLAlchemy engine and session factory for MySQL
    - Set up Alembic for migrations
    - Add APScheduler integration with FastAPI lifespan
    - _Requirements: 13.1_

  - [x] 1.2 Set up frontend project structure
    - Initialize React + TypeScript project with Vite
    - Install dependencies: react-router-dom, axios, idb, vite-plugin-pwa
    - Install dev dependencies: vitest, @testing-library/react, fast-check
    - Create directory structure: `frontend/src/{pages,components,services,hooks,utils,types,tests}`
    - Configure mobile-first responsive layout (360px+ viewport)
    - Set up React Router with page shells
    - _Requirements: 14.3_

  - [x] 1.3 Create SQLAlchemy ORM models and initial Alembic migration
    - Implement models: User, UserLocale, Transaction, Category, DailyTask, Budget, BudgetPeriodRecord, Notification, SpikeSuppression, CoachingSuggestion
    - Store monetary amounts as integers (smallest currency unit) with `currency_code` field
    - Store all timestamps in UTC; add `transaction_date_local` for date queries
    - Use enums for DailyTask.status, completion_type, Budget.period_type, CoachingSuggestion.status
    - Add version column on User for optimistic locking on streak
    - Generate and apply initial Alembic migration with proper indexes
    - _Requirements: 13.1, 13.5, 13.6, 14.8_

  - [x] 1.4 Implement LocaleService and locale configuration data
    - Create `app/services/locale_service.py` with `LOCALE_CONFIGS` dictionary
    - Support at minimum: US, GB, JP, IN, DE, FR, BR, AU, CA, KR
    - Implement `get_locale_config(country_code)` → complete LocaleConfig
    - Implement `format_amount(amount_smallest_unit, locale)` → display string
    - Implement `parse_amount_input(input_str, locale)` → integer smallest unit
    - Implement `get_week_boundaries(date, locale)` → (start, end) tuple
    - Implement amount validator (positive, correct decimal precision per currency)
    - _Requirements: 14.2, 14.3, 14.4, 14.5, 14.6, 14.9_

  - [x]* 1.5 Write property tests for LocaleService (backend - Hypothesis)
    - **Property 1: Amount formatting round-trip**
    - **Property 2: Amount validation by locale**
    - **Property 16: Timestamp UTC round-trip**
    - **Property 17: Locale configuration completeness**
    - **Property 19: Week boundary calculation by locale**
    - **Validates: Requirements 5.8, 8.9, 13.5, 13.6, 14.2, 14.3, 14.4, 14.5, 14.9**

  - [x] 1.6 Implement frontend locale utilities and shared components
    - Create `src/types/locale.ts` with LocaleConfig interface
    - Create `src/utils/locale.ts` with `formatAmount()`, `parseAmountInput()`, `formatDate()`, `getWeekBoundaries()`
    - Create `src/components/AmountInput.tsx` — currency symbol prefix/suffix, decimal precision enforcement, real-time validation
    - Create `src/components/CurrencyDisplay.tsx` — integer → locale-formatted display string
    - _Requirements: 3.8, 14.3, 14.4, 14.5, 14.6_

  - [x]* 1.7 Write property tests for frontend locale utilities (fast-check)
    - **Property 1: Amount formatting round-trip (CurrencyDisplay + AmountInput)**
    - **Property 2: Amount validation by locale (AmountInput component)**
    - **Property 18: Date formatting by locale**
    - **Validates: Requirements 5.8, 8.9, 13.6, 14.3, 14.6**

  - [x] 1.8 Implement locale API endpoints and onboarding gate
    - Create Pydantic schemas for locale config request/response
    - `GET /api/settings/locale` — return current locale config
    - `PUT /api/settings/locale` — update country, cascade locale settings
    - Implement `OnboardingPage` with country selector
    - Block access to main interface until country is selected
    - _Requirements: 14.1, 14.7, 14.10_

- [x] 2. Checkpoint - Foundations complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Transaction logging (Quick_Add)
  - [x] 3.1 Implement TransactionService backend
    - `create_transaction` — validate amount (positive, correct precision per currency), persist with currency_code
    - `get_transactions` — query with date range, category, and limit filters
    - `get_frequent_categories` — top 5 categories by usage in last 30 days
    - Database retry logic: 3 attempts with exponential backoff (max 2s between)
    - Auto-assign current UTC datetime; store transaction_date_local
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 13.1, 13.2, 13.3, 13.6_

  - [x] 3.2 Create transaction API endpoints
    - `POST /api/transactions` — create (validate, persist, return confirmation)
    - `GET /api/transactions` — list with filters
    - `GET /api/transactions/frequent-categories` — top 5
    - Define Pydantic request/response schemas
    - Return 422 with field-level errors for invalid amounts (indicating currency constraints)
    - _Requirements: 3.1, 3.4, 3.5, 3.6, 13.3, 13.4_

  - [x]* 3.3 Write property test for frequent categories (backend - Hypothesis)
    - **Property 6: Frequent categories top-N**
    - **Validates: Requirements 3.5**

  - [x] 3.4 Implement QuickAddPage frontend
    - Single-screen layout: AmountInput, direction toggle (spent/received), save button — no scrolling required
    - Display up to 5 frequent category shortcut buttons
    - Optional fields: category selector, note (max 200 chars), payment method, tags (max 10)
    - Show currency symbol per locale convention
    - On validation error: highlight invalid fields, retain all input, display error message
    - On success: show confirmation within 2 seconds
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8_

- [x] 4. Category suggestion
  - [x] 4.1 Implement category suggestion logic
    - Add `suggest_category(user_id, note, amount)` to TransactionService
    - Priority: user override → exact note match → 10% amount proximity
    - Return None if user has fewer than 5 categorized transactions
    - Track and query user override history
    - _Requirements: 4.1, 4.3, 4.4_

  - [x] 4.2 Implement category suggestion API and frontend integration
    - `POST /api/transactions/suggest-category` endpoint
    - Display suggestion as pre-selected category on QuickAddPage (zero-tap accept)
    - Allow single-tap override; record override for future priority
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x]* 4.3 Write property test for category suggestion (backend - Hypothesis)
    - **Property 7: Category suggestion pattern matching**
    - **Validates: Requirements 4.1, 4.3, 4.4**

- [x] 5. Daily task and streak mechanics
  - [x] 5.1 Implement DailyTaskService backend
    - `generate_daily_task(user_id, date)` — create pending task for new day
    - `complete_task(task_id, completion_type)` — transition pending/grace_period → completed
    - `get_current_task(user_id)` — return today's task with hours remaining
    - `check_grace_period(user_id)` — evaluate yesterday's task, compute remaining time
    - Auto-complete daily task when transaction is logged for current day
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6_

  - [x] 5.2 Implement StreakService backend
    - `get_current_streak(user_id)` — read current streak count
    - `increment_streak(user_id)` — increment with optimistic locking (version column)
    - `reset_streak(user_id)` — set to zero
    - `evaluate_missed_days(user_id)` — handle grace period, multi-day misses
    - Grace period: 24-hour window; only most recent missed day recoverable
    - _Requirements: 1.6, 2.1, 2.2, 2.3, 2.5_

  - [x]* 5.3 Write property tests for streak and daily task (backend - Hypothesis)
    - **Property 3: Streak state machine correctness**
    - **Property 4: Grace period remaining time calculation**
    - **Property 5: Daily task completion on transaction**
    - **Validates: Requirements 1.2, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5**

  - [x] 5.4 Implement daily task API endpoints and scheduler job
    - `GET /api/daily-task` — current task with hours remaining
    - `POST /api/daily-task/complete` — mark as "no transactions"
    - `GET /api/streak` — current streak info
    - Register APScheduler job: check every 60s, generate tasks for users whose midnight has passed
    - Wire transaction creation to auto-complete current day's task
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 5.5 Implement daily task and streak frontend UI
    - Create `StreakBadge` component — current streak count with visual indicator
    - Create `DailyTaskBanner` — incomplete task with hours remaining, "no transactions" single-tap button
    - Grace period visual: remaining hours/minutes countdown
    - Integrate into HomePage
    - _Requirements: 1.2, 1.3, 1.4, 2.4_

- [x] 6. Checkpoint - Core logging and habits complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Budget creation and management
  - [x] 7.1 Implement BudgetService backend
    - Create budget: validate limit (positive, correct precision), enforce uniqueness per category/period
    - Track BudgetPeriodRecord: update spent_smallest_unit on each transaction
    - Auto-rollover: create new period with same limit when current period ends
    - Calculate projection: `(spent / days_elapsed) * total_days`; on/off track status
    - Handle zero days elapsed: on_track, remaining = full limit
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 8.1, 8.2, 8.6, 8.7, 8.8_

  - [x] 7.2 Implement budget threshold notifications
    - Fire 80% notification exactly once per budget period when threshold first crossed
    - Fire 100% notification exactly once per budget period when threshold first crossed
    - Use idempotency keys (budget_id + period_start + threshold) to prevent duplicates
    - _Requirements: 8.3, 8.4_

  - [x]* 7.3 Write property tests for budget logic (backend - Hypothesis)
    - **Property 10: Budget projection and on/off track status**
    - **Property 11: Budget threshold notifications fire exactly once per crossing**
    - **Property 12: Budget period rollover preserves limit**
    - **Validates: Requirements 7.1, 7.3, 7.4, 7.5, 8.3, 8.4, 8.6, 8.7**

  - [x] 7.4 Create budget API endpoints
    - `GET /api/budgets` — list active budgets with status and projection
    - `POST /api/budgets` — create (validate, check duplicates, return 409 on conflict)
    - `PUT /api/budgets/{id}` — update limit
    - `DELETE /api/budgets/{id}` — deactivate
    - Return 422 on invalid limit, 409 on duplicate
    - _Requirements: 8.1, 8.2, 8.5, 8.6, 8.7, 8.8_

  - [x] 7.5 Implement BudgetsPage and BudgetCard frontend
    - BudgetsPage: list active budgets, create new budget form (category, period, limit)
    - BudgetCard: money left indicator, on/off track status, projected overage amount
    - Real-time update after transaction save (refresh within 2 seconds)
    - Format all amounts using locale currency settings
    - Validation errors for invalid limits
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.8, 8.9_

- [x] 8. Periodic spending summaries and spike detection
  - [x] 8.1 Implement InsightEngine - periodic summaries
    - `generate_weekly_summary(user_id, week_end_date)` — total spent, received, net, per-category totals
    - `generate_monthly_summary(user_id, month, year)` — weekly fields + absolute/percentage diff vs prior month
    - Percentage change: round to 1 decimal; "new" when previous is zero
    - Handle zero-activity periods (generate summary with zero values)
    - Handle first period (no comparison data available)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 5.8_

  - [x] 8.2 Implement InsightEngine - spending spike detection
    - `detect_spending_spikes(user_id)` — flag categories where current week > 150% of 4-week rolling average
    - Skip categories with fewer than 4 weeks of history
    - Enforce at-most-one alert per category per week via SpikeSuppression table
    - _Requirements: 6.1, 6.2, 6.5_

  - [x]* 8.3 Write property tests for insights (backend - Hypothesis)
    - **Property 8: Periodic summary aggregation**
    - **Property 9: Spending spike detection**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 6.1, 6.2, 6.5**

  - [x] 8.4 Create insight API endpoints and scheduler jobs
    - `GET /api/insights/weekly` — current/past weekly summaries
    - `GET /api/insights/monthly` — current/past monthly summaries
    - `GET /api/insights/spikes` — active spike alerts
    - Register APScheduler jobs: weekly summary at week end, monthly at month end, spike detection daily
    - Generate in-app notification within 1 hour of summary/spike generation
    - _Requirements: 5.1, 5.2, 5.6, 6.1, 6.3_

  - [x] 8.5 Implement InsightsPage frontend
    - Display weekly and monthly summaries with category breakdowns
    - Show percentage changes vs prior period (or "new" indicator)
    - Display spike alerts: category name, current total, 4-week average
    - Format all amounts using locale settings
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.8, 6.4_

- [x] 9. Checkpoint - Budgets and insights complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. AI assistant integration
  - [x] 10.1 Implement AIAssistantService - recommendations and queries
    - Build data context assembly (aggregate transactions by category, never send raw notes to LLM)
    - `get_budget_recommendation(user_id)` — analyze 30-90 days; require 14+ days history; include categories with 3+ transactions
    - `answer_query(user_id, question)` — assemble relevant data context, query LLM, validate response against actual data
    - Handle LLM timeouts (15s recommendations, 10s queries) and rate limits
    - Return "insufficient data" when < 14 days history (specify days needed)
    - Return "out of scope" for non-financial queries with example suggestions
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x] 10.2 Implement AI proactive coaching service
    - `get_proactive_coaching(user_id)` — detect 20%+ deviation from pro-rated budget at midpoint
    - Generate per-budget suggestions with reasoning (deviation amount, pro-rated expected, historical patterns)
    - Dismiss logic: do not re-surface unless deviation increases by 10+ percentage points
    - Store CoachingSuggestion records (status: pending, accepted, dismissed)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x]* 10.3 Write property tests for AI eligibility and coaching (backend - Hypothesis)
    - **Property 13: AI data eligibility filtering**
    - **Property 14: Budget deviation detection and re-surfacing logic**
    - **Validates: Requirements 9.3, 9.4, 10.1, 10.4, 10.5**

  - [x] 10.4 Create AI API endpoints
    - `POST /api/ai/recommend-budget` — budget recommendation (rate limited)
    - `POST /api/ai/query` — natural language data query (rate limited)
    - `GET /api/ai/coaching` — pending proactive suggestions
    - `POST /api/ai/coaching/{id}/dismiss` — dismiss suggestion
    - Return timeout/unavailability errors with appropriate messages
    - _Requirements: 9.5, 9.6, 10.3, 10.5, 11.4, 11.5_

  - [x] 10.5 Implement AIChatPage frontend
    - Conversational UI: message input, response display with specific numbers and time ranges
    - Handle timeout with "assistant unavailable" message and retry button
    - Show "insufficient data" messages with days remaining
    - Display out-of-scope guidance with example questions
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x] 10.6 Implement AI coaching UI and budget recommendation flow
    - Display proactive suggestions with accept (single tap) and dismiss actions
    - Budget recommendation request with loading state (up to 15s)
    - Show reasoning with referenced data points
    - Show "more data needed" with days remaining when < 14 days history
    - _Requirements: 9.2, 9.3, 10.2, 10.3_

- [x] 11. Notification system
  - [x] 11.1 Implement notification backend service
    - Create Notification records for: daily reminders, budget thresholds, spike alerts, summary availability, AI coaching
    - `GET /api/notifications` — unread in-app notifications
    - `PUT /api/notifications/{id}/read` — mark as read
    - Schedule daily task reminder at user-configured time (default 8 PM local)
    - Enforce at-most-one reminder per day per user
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [x]* 11.2 Write property test for daily reminder (backend - Hypothesis)
    - **Property 15: Daily reminder at-most-once**
    - **Validates: Requirements 12.2**

  - [x] 11.3 Implement push notification delivery
    - `POST /api/notifications/push-subscription` — register VAPID push subscription
    - Send push for: daily_reminder, budget_80, budget_100, spike_alert, summary_ready, ai_coaching
    - Use notification tag to prevent duplicate push notifications of same type
    - Fall back to in-app only when push permission denied
    - _Requirements: 12.1, 12.3, 12.4, 12.5_

  - [x] 11.4 Implement notification preferences and frontend UI
    - Settings page: toggle push notifications independently of in-app
    - Default both enabled on first use
    - NotificationBanner component on HomePage for unread notifications
    - Display guidance message when push permission denied
    - _Requirements: 12.3, 12.4, 12.5_

- [x] 12. Checkpoint - AI and notifications complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. PWA offline support and service worker
  - [x] 13.1 Implement service worker with caching strategy
    - App Shell (HTML, JS, CSS): cache-first, precached on install
    - Locale configs: cache on first load
    - Recent transactions: network-first with stale fallback
    - Budget status: network-first with 5-minute cache fallback
    - Static assets: cache-first, stale-while-revalidate on new version
    - _Requirements: 13.1_

  - [x] 13.2 Implement offline transaction logging with IndexedDB
    - Save transactions to IndexedDB with `pending_sync` flag when offline
    - Show "saved offline, will sync" indicator in UI
    - Register Background Sync for transaction upload on connectivity return
    - Clear `pending_sync` flag on successful sync
    - Retry on next connectivity event (up to 24 hours, then prompt user)
    - Graceful degradation when IndexedDB unavailable (require connectivity, show banner)
    - _Requirements: 13.1, 13.2_

  - [x] 13.3 Implement push notification handling in service worker
    - Handle push events for all notification types
    - Display notification with icon (192px), badge (72px), action URL
    - Use tag to prevent duplicate notifications of same type
    - Handle notification click to open action URL
    - _Requirements: 12.1_

  - [x] 13.4 Configure Web App Manifest and installability
    - Create manifest.json: name, icons (192px, 512px), theme color, start_url, display: standalone
    - Ensure Chrome installability criteria met (service worker + manifest + HTTPS)
    - _Requirements: 14.1_

- [x] 14. Country change and historical data preservation
  - [x] 14.1 Implement country change in settings
    - SettingsPage: allow changing country selection
    - On change: update UserLocale, apply new locale to all new transactions and UI
    - Retain all existing transactions with original currency_code
    - Display historical amounts using stored currency_code (not new locale's currency)
    - _Requirements: 14.7, 14.8_

  - [x]* 14.2 Write property test for historical currency preservation (backend - Hypothesis)
    - **Property 20: Historical currency preservation on locale change**
    - **Validates: Requirements 14.8**

- [x] 15. Wire HomePage and final integration
  - [x] 15.1 Implement HomePage with all widgets
    - StreakBadge with current streak count
    - DailyTaskBanner (hours remaining or grace period countdown)
    - BudgetCard summaries for active budgets (money left, on/off track)
    - NotificationBanner for unread notifications
    - Quick navigation to QuickAdd, Budgets, Insights, AI Chat, Settings
    - _Requirements: 1.2, 7.1, 7.2, 12.1_

  - [x] 15.2 Wire all pages with navigation and error handling
    - Connect all pages via React Router with proper navigation flow
    - Implement global error boundary
    - API error handling: field-level errors on 4xx, generic toast with retry on 5xx
    - Graceful degradation when service worker registration fails (app continues without offline support)
    - _Requirements: 13.2, 14.10_

  - [x]* 15.3 Write integration tests for critical flows
    - Transaction save and read-back from database
    - Budget creation → transaction → projection update → threshold notification
    - Daily task generation via scheduler at midnight
    - Locale change and formatting verification for new vs historical transactions
    - AI endpoint timeout handling and error responses
    - _Requirements: 3.4, 7.2, 1.1, 14.7, 9.6_

- [x] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. User profile, category weights, and data layer
  - [x] 17.1 Add profile fields to User model and create new models + Alembic migration
    - Add columns to User model: `employment_status` (nullable enum: student, working, both), `commute_method` (nullable enum: public_transit, own_vehicle, walking_biking, none_remote), `vehicle_type` (nullable enum: motorcycle, car), `profile_completed` (boolean, default False)
    - Create `CategoryWeight` model: id, user_id (FK), category_name (string, unique per user), weight_percentage (Decimal 4,2), is_manual_override (boolean, default False), created_at_utc, updated_at_utc
    - Create `BudgetLimitChangeLog` model: id, budget_id (FK), old_limit_smallest_unit (int), new_limit_smallest_unit (int), reason (string), source_transaction_id (FK to Transaction), created_at_utc
    - Generate new Alembic migration (002_profile_weights_changelog.py) applying all schema changes
    - Update `backend/app/models/__init__.py` to export new models
    - _Requirements: 15.4, 16.1, 16.7, 17.3_

  - [x] 17.2 Create Pydantic schemas for profile, weights, and dashboard
    - Create `backend/app/schemas/profile.py`: LifestyleProfileInput (employment_status, commute_method, vehicle_type), LifestyleProfileResponse
    - Create `backend/app/schemas/weight.py`: CategoryWeightResponse, CategoryWeightOverrideRequest (category_name, new_percentage), WeightListResponse
    - Create `backend/app/schemas/dashboard.py`: PeriodSummaryResponse (period_type, total_income, total_expenses, balance, category_breakdown), PersonalizedInsightResponse
    - Add validation: vehicle_type required only when commute_method = own_vehicle; weight percentage between 0 and 100 exclusive
    - _Requirements: 15.2, 15.3, 16.1, 18.2_

  - [x] 17.3 Implement Weight_Rules_Table as configurable structure
    - Create `backend/app/services/weight_rules.py` with `WEIGHT_RULES_TABLE` dictionary
    - Key structure: Tuple[employment_status, commute_method, Optional[vehicle_type]]
    - Value: Dict[str, Decimal] mapping category_name → weight_percentage
    - Use placeholder Decimal values (structure is final, numbers are configurable)
    - Include all 15 profile combinations (3 employment × 5 commute variants)
    - Ensure every entry includes at minimum: Savings, Wants, Transportation, Food
    - Include fallback logic: equal distribution if lookup key not found
    - _Requirements: 16.2, 16.3_

- [x] 18. Backend services for profile and category weights
  - [x] 18.1 Implement ProfileService
    - Create `backend/app/services/profile_service.py`
    - `get_profile(user_id)` → reads employment_status, commute_method, vehicle_type from User
    - `update_profile(user_id, profile_input)` → validates input, stores on User record, sets profile_completed=True, calls `CategoryWeightService.recompute_weights(user_id)`
    - Validate: vehicle_type must be None unless commute_method = own_vehicle
    - _Requirements: 15.4, 15.5, 15.6_

  - [x] 18.2 Implement CategoryWeightService
    - Create `backend/app/services/category_weight_service.py`
    - `get_weights(user_id)` → returns all CategoryWeight entries for user
    - `derive_defaults(profile)` → pure function: looks up Weight_Rules_Table, returns list of CategoryWeight dicts summing to 100%
    - `recompute_weights(user_id)` → fetches profile, calls derive_defaults, replaces non-manually-overridden entries, redistributes to maintain 100% sum, persists
    - `override_weight(user_id, category_name, new_percentage)` → sets specified category to new_percentage, redistributes remaining non-overridden categories proportionally, marks is_manual_override=True, validates sum=100%, persists
    - `validate_weights(weights)` → asserts sum == Decimal("100.00")
    - Use Decimal arithmetic throughout (no floats)
    - Handle edge case: all other categories manually overridden → return 422 error
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7_

  - [x]* 18.3 Write property tests for profile and weights (backend - Hypothesis)
    - **Property 21: Profile persistence and weight recomputation trigger**
    - **Property 22: Category weight sum invariant**
    - **Property 23: Default weight derivation includes minimum categories**
    - **Property 24: Manual weight override redistributes proportionally and flags correctly**
    - **Validates: Requirements 15.4, 15.6, 16.1, 16.2, 16.3, 16.5, 16.6, 16.7**

- [x] 19. Dynamic budget recalculation on income
  - [x] 19.1 Extend BudgetService with recalculate_on_income method
    - Add `recalculate_on_income(user_id, income_transaction)` to existing `backend/app/services/budget_service.py`
    - For each active budget with a matching CategoryWeight entry: new_limit = floor(weight_percentage / 100 × available_balance)
    - Compute available_balance as sum(received) - sum(spent) across all user transactions
    - Only update budgets where new_limit != old_limit
    - Create BudgetLimitChangeLog entry atomically with each budget limit update
    - Log reason: f"Income received: {amount} from transaction #{transaction_id}"
    - Existing projection/on-track logic (Property 10) continues unchanged with dynamic limit
    - Do NOT modify stored CategoryWeight percentages
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [x] 19.2 Wire income transaction to budget recalculation trigger
    - In TransactionService.create_transaction (or transaction API endpoint): after persisting a transaction with direction="received", call `BudgetService.recalculate_on_income(user_id, transaction)`
    - Ensure recalculation runs within the same request (no async job needed — limits change immediately)
    - After recalculation, trigger existing budget threshold notification logic for any budgets whose new limits cross 80%/100% thresholds
    - _Requirements: 17.1, 17.3_

  - [x]* 19.3 Write property tests for budget recalculation (backend - Hypothesis)
    - **Property 25: Budget recalculation on income preserves weight percentages**
    - **Property 26: Budget limit change audit logging**
    - **Validates: Requirements 17.1, 17.2, 17.3**

- [x] 20. Checkpoint - Profile, weights, and recalculation backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 21. API endpoints for profile, weights, and dashboard
  - [x] 21.1 Create profile API endpoints
    - `GET /api/profile` → returns current LifestyleProfile (or 404 if not set)
    - `PUT /api/profile` → creates or updates profile; triggers weight recomputation; returns updated profile
    - Add profile onboarding gate middleware: if user.profile_completed=False and route is not /api/profile or /api/settings/locale, return 403 with message "Profile onboarding required"
    - _Requirements: 15.1, 15.4, 15.5_

  - [x] 21.2 Create weights API endpoints
    - `GET /api/weights` → returns all CategoryWeight entries for user
    - `PUT /api/weights/{category_name}` → manually override a single weight; returns updated full weight list
    - `POST /api/weights/reset` → clears all manual overrides, recomputes from profile defaults; returns new weight list
    - Return 422 if override would leave no categories available for redistribution
    - Return 400 if profile not completed (weights cannot be derived)
    - _Requirements: 16.1, 16.4, 16.5, 16.6_

  - [x] 21.3 Create dashboard API endpoints
    - `GET /api/dashboard/summary?period={daily|weekly|monthly}` → returns PeriodSummary scoped to selected period
    - `GET /api/dashboard/insight` → returns personalized insight string based on user profile and weights
    - Period summary delegates to existing InsightEngine methods for weekly/monthly; adds daily aggregation path
    - Personalized insight selects contextual tip based on highest-weight category and current spending
    - _Requirements: 18.1, 18.2, 18.3, 18.4_

  - [x]* 21.4 Write property test for period-scoped dashboard (backend - Hypothesis)
    - **Property 27: Period-scoped dashboard aggregation**
    - **Validates: Requirements 18.2**

- [x] 22. Extend InsightEngine for period-scoped queries and personalized insights
  - [x] 22.1 Add period-scoped summary method to InsightEngine
    - Add `get_period_summary(user_id, period_type, reference_date)` to existing `backend/app/services/insight_engine.py`
    - For "daily": aggregate transactions for the reference_date only
    - For "weekly": delegate to existing `generate_weekly_summary`
    - For "monthly": delegate to existing `generate_monthly_summary`
    - Return unified PeriodSummary structure for all period types
    - Do NOT duplicate aggregation logic — call existing methods
    - _Requirements: 18.2, 18.3_

  - [x] 22.2 Add personalized insight method to InsightEngine
    - Add `get_personalized_insight(user_id, profile, weights)` to existing `backend/app/services/insight_engine.py`
    - Logic: find user's highest-weight category, compare spending against budget limit, generate contextual tip
    - Savings-focused tip if Savings weight is highest and savings goal not met
    - Spending moderation tip if Wants weight is highest and approaching limit
    - Transportation tip if Transportation is highest (vehicle owner)
    - Default: generic encouragement based on overall on-track status
    - _Requirements: 18.4_

- [x] 23. Frontend - Profile onboarding and settings
  - [x] 23.1 Implement ProfileOnboardingPage
    - Create `frontend/src/pages/ProfileOnboardingPage.tsx`
    - Form fields: employment_status radio group (Student, Working, Both), commute_method radio group (Public Transit, Own Vehicle, Walking/Biking, None/Remote)
    - Conditional field: vehicle_type selector (Motorcycle, Car) shown only when commute_method = "own_vehicle"
    - On submit: PUT /api/profile → on success navigate to main dashboard
    - Display after locale onboarding completes, gate dashboard access until profile_completed
    - Add to React Router after OnboardingPage route
    - _Requirements: 15.1, 15.2, 15.3_

  - [x] 23.2 Implement ProfileSettings component
    - Create `frontend/src/pages/ProfileSettings.tsx`
    - Accessible from SettingsPage
    - Display current profile values, allow editing with same conditional vehicle_type logic
    - On save: PUT /api/profile → show success confirmation, weights recomputed in background
    - _Requirements: 15.5, 15.6_

  - [x] 23.3 Implement WeightSettings component
    - Create `frontend/src/pages/WeightSettings.tsx`
    - Accessible from SettingsPage
    - Display all CategoryWeight entries with current percentages (formatted as XX.XX%)
    - Allow manual override: input field per category with "Save" action
    - Show redistribution preview before confirmation (call API to validate, display new values)
    - Visually flag manually-overridden entries (e.g., badge or different color)
    - "Reset to defaults" button → POST /api/weights/reset
    - _Requirements: 16.4, 16.5, 16.7_

- [x] 24. Frontend - Extended HomePage with period selector
  - [-] 24.1 Add period selector and dashboard summary to HomePage
    - Add dropdown at top of existing HomePage: Daily | Weekly | Monthly (default: Daily)
    - Below selector: display current balance, total income, total expenses for selected period
    - Fetch data from GET /api/dashboard/summary?period={selected}
    - Display per-category budget list using existing BudgetCard component
    - Reuse existing CurrencyDisplay for all amounts
    - Maintain existing HomePage widgets (StreakBadge, DailyTaskBanner, NotificationBanner)
    - _Requirements: 18.1, 18.2, 18.5_

  - [x] 24.2 Add personalized insight banner to HomePage
    - Fetch from GET /api/dashboard/insight
    - Display one insight banner at the top of the dashboard (below period selector, above budget cards)
    - Style consistent with existing BudgetCard/NotificationBanner components
    - Show contextual tip driven by Lifestyle_Profile
    - Handle loading/error states gracefully (hide banner if insight unavailable)
    - _Requirements: 18.4, 18.5_

- [x] 25. Checkpoint - Full integration of Requirements 15-18
  - Ensure all tests pass, ask the user if questions arise.

- [x] 26. Integration wiring and final verification
  - [x] 26.1 Wire onboarding flow end-to-end
    - Verify flow: Locale onboarding → Profile onboarding → Dashboard
    - Ensure profile_completed gate blocks dashboard access correctly
    - Ensure weight derivation triggers on first profile submission
    - Test: new user → select country → fill profile → see dashboard with budget cards reflecting derived weights
    - _Requirements: 15.1, 15.6, 16.3_

  - [x] 26.2 Wire income transaction → recalculation → notification flow
    - Verify: log income transaction → budgets recalculated → change logs created → BudgetCard updated → threshold notifications fire if applicable
    - Test with multiple active budgets and varying weight distributions
    - Ensure existing budget projection logic works correctly with dynamic limits
    - _Requirements: 17.1, 17.3, 17.4_

  - [ ]* 26.3 Write integration tests for Requirements 15-18 flows
    - Profile submission → weight derivation → budget creation flow
    - Income transaction → budget recalculation → change log creation → notification
    - Period selector switch → correct aggregation scoping
    - Weight override → redistribution → budget limit recalculation cascade
    - Profile edit → weight recomputation for non-overridden categories only
    - _Requirements: 15.6, 16.5, 17.1, 18.2_

- [x] 27. Final checkpoint - Requirements 15-18 complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at logical boundaries
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend: Python (FastAPI + SQLAlchemy + MySQL) with Hypothesis for property-based tests
- Frontend: React + TypeScript with fast-check for property-based tests and Vitest for unit tests
- All monetary amounts stored as integers in smallest currency unit (e.g., cents for USD, yen for JPY)
- All timestamps stored in UTC, converted to user timezone for display
- The LLM API integration uses structured prompts with aggregated data context (never raw transaction notes)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["1.4", "1.6"] },
    { "id": 3, "tasks": ["1.5", "1.7", "1.8"] },
    { "id": 4, "tasks": ["3.1"] },
    { "id": 5, "tasks": ["3.2", "3.4"] },
    { "id": 6, "tasks": ["3.3", "4.1"] },
    { "id": 7, "tasks": ["4.2", "4.3"] },
    { "id": 8, "tasks": ["5.1", "5.2"] },
    { "id": 9, "tasks": ["5.3", "5.4"] },
    { "id": 10, "tasks": ["5.5"] },
    { "id": 11, "tasks": ["7.1"] },
    { "id": 12, "tasks": ["7.2", "7.3", "7.4"] },
    { "id": 13, "tasks": ["7.5"] },
    { "id": 14, "tasks": ["8.1", "8.2"] },
    { "id": 15, "tasks": ["8.3", "8.4"] },
    { "id": 16, "tasks": ["8.5"] },
    { "id": 17, "tasks": ["10.1", "10.2"] },
    { "id": 18, "tasks": ["10.3", "10.4"] },
    { "id": 19, "tasks": ["10.5", "10.6"] },
    { "id": 20, "tasks": ["11.1"] },
    { "id": 21, "tasks": ["11.2", "11.3"] },
    { "id": 22, "tasks": ["11.4"] },
    { "id": 23, "tasks": ["13.1", "13.4"] },
    { "id": 24, "tasks": ["13.2", "13.3"] },
    { "id": 25, "tasks": ["14.1"] },
    { "id": 26, "tasks": ["14.2", "15.1"] },
    { "id": 27, "tasks": ["15.2"] },
    { "id": 28, "tasks": ["15.3"] },
    { "id": 29, "tasks": ["17.1", "17.2", "17.3"] },
    { "id": 30, "tasks": ["18.1", "18.2"] },
    { "id": 31, "tasks": ["18.3", "19.1"] },
    { "id": 32, "tasks": ["19.2", "19.3"] },
    { "id": 33, "tasks": ["21.1", "21.2", "22.1"] },
    { "id": 34, "tasks": ["21.3", "22.2"] },
    { "id": 35, "tasks": ["21.4", "23.1"] },
    { "id": 36, "tasks": ["23.2", "23.3"] },
    { "id": 37, "tasks": ["24.1"] },
    { "id": 38, "tasks": ["24.2"] },
    { "id": 39, "tasks": ["26.1", "26.2"] },
    { "id": 40, "tasks": ["26.3"] }
  ]
}
```
