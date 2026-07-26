# Requirements Document

## Introduction

Daily Money Tracker is a mobile-first personal finance application that makes daily income and expense logging effortless and habitual. The application generates a daily logging task to ensure consistent tracking, provides automatic spending insights, supports budget creation and monitoring, and includes an AI budgeting assistant that coaches users based on their actual financial data. The app personalizes the experience based on the user's country, adapting currency formatting, date conventions, and locale-specific defaults. The core goal is to eliminate the "where did my money go?" moment by surfacing insights automatically and making logging fast enough (under 30 seconds) that skipping it is never tempting.

## Glossary

- **Tracker**: The Daily Money Tracker application system
- **Transaction**: A single financial event representing money spent or received, with an amount, direction, and optional metadata
- **Daily_Task**: A logging task automatically generated each calendar day that the user must complete by logging transactions or confirming no transactions occurred
- **Category**: A classification label for a transaction (e.g., food, transport, entertainment)
- **Budget**: A spending limit set by the user for a specific category or overall, bound to a time period (weekly or monthly)
- **Budget_Period**: The time window (week or month) over which a budget applies
- **Streak**: A count of consecutive days where the user has completed their Daily_Task
- **Grace_Period**: A 24-hour window after a missed day during which the user can retroactively log and preserve their streak
- **Insight_Engine**: The subsystem that analyzes transaction data to produce summaries, trends, and anomaly alerts
- **AI_Assistant**: The conversational AI subsystem that provides budget recommendations, spending analysis, and coaching based on the user's historical data
- **Quick_Add**: A streamlined transaction entry interface requiring minimal taps to log a transaction
- **Spending_Spike**: A category spend that exceeds 150% of the rolling 4-week average for that category
- **User_Locale**: The user's configured country and associated regional settings including currency, date format, number format, and week start day
- **Currency**: The monetary unit determined by the user's country (e.g., USD, EUR, JPY, INR), including its ISO 4217 code, symbol, decimal precision, decimal separator, and thousands separator
- **Lifestyle_Profile**: The user's answers to the personalization questionnaire (employment status, commute method, vehicle type) stored on their User record
- **Category_Weight**: A percentage-based allocation for a budget category, per user, summing to 100% across all categories
- **Weight_Rules_Table**: A predefined mapping of profile answer combinations to default category weight distributions

## Requirements

### Requirement 1: Daily Task Generation

**User Story:** As a user, I want a logging task to appear every day automatically, so that I never forget to track my spending.

#### Acceptance Criteria

1. WHEN a new calendar day begins (midnight in the user's configured timezone), THE Tracker SHALL generate a new Daily_Task for that day within 60 seconds.
2. WHEN the user opens the Tracker and the current Daily_Task is incomplete, THE Tracker SHALL display the Daily_Task on the home screen as a banner or badge indicating the number of hours remaining in the current day.
3. WHILE the current Daily_Task is incomplete, THE Tracker SHALL display a "no transactions" option that the user can select with a single tap to confirm no transactions occurred that day.
4. WHEN the user marks the Daily_Task as "no transactions", THE Tracker SHALL record the Daily_Task as completed for that day.
5. WHEN the user logs at least one transaction for the current day, THE Tracker SHALL mark the Daily_Task as completed for that day.
6. WHEN the Daily_Task transitions from incomplete to completed (by logging at least one transaction or confirming no transactions), THE Tracker SHALL increment the user's Streak by one day.

### Requirement 2: Missed Day and Streak Recovery

**User Story:** As a user, I want to be able to recover from a missed day without losing my entire streak, so that one slip doesn't destroy my motivation.

#### Acceptance Criteria

1. IF the user does not complete the Daily_Task by the end of the calendar day (23:59:59 in the user's configured timezone), THEN THE Tracker SHALL mark that day as missed and retain the Daily_Task for retroactive completion during the Grace_Period starting at 00:00:00 of the following day.
2. WHEN the user completes a missed Daily_Task within the 24-hour Grace_Period, THE Tracker SHALL preserve the user's Streak without penalty.
3. IF the user does not complete a missed Daily_Task within the Grace_Period, THEN THE Tracker SHALL reset the Streak to zero.
4. WHEN a day is missed and the Grace_Period has not expired, THE Tracker SHALL display a visual indicator showing the remaining hours and minutes to recover the Streak.
5. IF the user misses multiple consecutive days, THEN THE Tracker SHALL only allow recovery of the most recent missed day within its Grace_Period and reset the Streak for all prior missed days.

### Requirement 3: Transaction Logging

**User Story:** As a user, I want to log a transaction with minimal effort, so that tracking my finances takes under 30 seconds.

#### Acceptance Criteria

1. WHEN the user initiates transaction logging, THE Tracker SHALL require only an amount (positive numeric value with decimal places matching the Currency decimal precision defined by the User_Locale) and a direction (spent or received) to save the transaction.
2. WHEN the user logs a transaction, THE Tracker SHALL allow the user to optionally add a category, a text note (maximum 200 characters), a payment method, and up to 10 tags.
3. WHEN the user opens the Quick_Add interface, THE Tracker SHALL display the amount input, direction toggle, and save button on a single screen without scrolling.
4. WHEN the user logs a transaction, THE Tracker SHALL complete the save operation and return confirmation within 2 seconds.
5. WHEN the user has previously logged transactions, THE Tracker SHALL display up to 5 most frequently used categories from the last 30 days as shortcut buttons on the Quick_Add interface.
6. IF the user submits a transaction with an invalid amount (non-numeric, zero, negative, or exceeding the maximum amount for the configured Currency), THEN THE Tracker SHALL prevent the save, display an error message indicating the amount is invalid, and retain all entered field values.
7. WHEN the user saves a transaction, THE Tracker SHALL automatically assign the current date and time to the transaction.
8. WHEN displaying the amount input field, THE Tracker SHALL show the Currency symbol for the user's configured User_Locale as a prefix or suffix according to the locale convention.

### Requirement 4: Category Suggestion

**User Story:** As a user, I want the app to suggest a category based on my past entries, so that I can categorize transactions faster.

#### Acceptance Criteria

1. WHEN the user enters a transaction note that exactly matches a previously categorized transaction's note, or an amount within 10% of a previously categorized transaction's amount, THE Tracker SHALL suggest the most frequently used category for that match.
2. WHEN the Tracker suggests a category, THE Tracker SHALL display the suggestion as a pre-selected option that the user can accept with zero additional taps or override by selecting a different category.
3. WHEN the user has fewer than 5 categorized transactions in their history, THE Tracker SHALL not display category suggestions.
4. WHEN the user overrides a suggested category, THE Tracker SHALL prioritize the overridden category for future transactions with the same note or amount pattern.

### Requirement 5: Periodic Spending Summary

**User Story:** As a user, I want automatic spending summaries at the end of each week and month, so that I never have to manually reconstruct where my money went.

#### Acceptance Criteria

1. WHEN a calendar week ends (the day before the User_Locale week start day, at 23:59 in the user's configured timezone), THE Insight_Engine SHALL generate a weekly spending summary that includes total spent, total received, net balance, and spending totals grouped by category.
2. WHEN a calendar month ends (last day of the month, 23:59 in the user's configured timezone), THE Insight_Engine SHALL generate a monthly spending summary that includes total spent, total received, net balance, spending by category, and the absolute and percentage difference per category compared to the prior month.
3. WHEN a periodic summary is generated and a previous equivalent period exists, THE Insight_Engine SHALL include the percentage change in each category compared to the previous equivalent period, rounded to one decimal place.
4. IF a category had no spending in the previous equivalent period but has spending in the current period, THEN THE Insight_Engine SHALL indicate that category as new for the current period instead of calculating a percentage change.
5. IF no transactions exist for a given period, THEN THE Insight_Engine SHALL generate a summary indicating zero activity for that period rather than omitting the summary.
6. WHEN a periodic summary is available, THE Tracker SHALL notify the user within 1 hour of the summary being generated.
7. IF no previous equivalent period exists (first week or first month of usage), THEN THE Insight_Engine SHALL generate the summary without comparison data and indicate that no prior period is available for comparison.
8. WHEN a periodic summary is displayed, THE Insight_Engine SHALL format all monetary amounts using the Currency symbol, decimal separator, thousands separator, and decimal precision defined by the User_Locale.

### Requirement 6: Spending Anomaly Detection

**User Story:** As a user, I want to be alerted when my spending in a category spikes unexpectedly, so that I can catch overspending before it becomes a problem.

#### Acceptance Criteria

1. WHEN spending in a category within the current calendar week reaches a Spending_Spike (exceeds 150% of the rolling 4-week average for that category), THE Insight_Engine SHALL flag the anomaly and generate an alert.
2. IF the user has fewer than 4 weeks of transaction history in a category, THEN THE Insight_Engine SHALL not evaluate that category for Spending_Spike detection.
3. WHEN a Spending_Spike alert is generated, THE Tracker SHALL notify the user proactively via in-app notification within 1 hour of the spike being detected.
4. WHEN a Spending_Spike alert is displayed, THE Tracker SHALL show the category name, the current period total, and the 4-week average for comparison.
5. THE Insight_Engine SHALL generate at most one Spending_Spike alert per category per calendar week to avoid duplicate notifications.

### Requirement 7: Budget Status Indicator

**User Story:** As a user, I want to see at a glance whether I'm on track with my budget, so that I can make informed spending decisions throughout the day.

#### Acceptance Criteria

1. WHEN the user opens the Tracker and an active Budget exists, THE Tracker SHALL display a "money left" indicator showing the remaining budget amount (budget limit minus total spent in the current Budget_Period) for each active Budget.
2. WHEN the user logs a transaction that applies to an active Budget, THE Tracker SHALL update the "money left" indicator and the on/off track status within 2 seconds without requiring the user to reload or re-open the Tracker.
3. IF the projected period spend (total spent in current Budget_Period divided by days elapsed, multiplied by total days in the Budget_Period) exceeds the budget limit, THEN THE Tracker SHALL display an "off track" status with the projected overage amount (projected spend minus budget limit).
4. IF the projected period spend is less than or equal to the budget limit, THEN THE Tracker SHALL display an "on track" status.
5. IF the current Budget_Period has zero days elapsed (first day of period with no full day completed), THEN THE Tracker SHALL display the "on track" status and show the full budget limit as the remaining amount until at least one day of spending data is available.

### Requirement 8: Budget Creation and Management

**User Story:** As a user, I want to create budgets for specific categories or overall spending, so that I can set limits and track progress against them.

#### Acceptance Criteria

1. WHEN the user creates a budget, THE Tracker SHALL allow the user to set a spending limit (positive numeric value with decimal places matching the Currency decimal precision defined by the User_Locale) for a specific category or for overall spending.
2. WHEN the user creates a budget, THE Tracker SHALL require the user to select a Budget_Period of either weekly or monthly.
3. WHEN spending reaches 80% of a budget limit, THE Tracker SHALL send the user a notification indicating the budget is approaching its limit (once per Budget_Period per threshold).
4. WHEN spending exceeds 100% of a budget limit, THE Tracker SHALL send the user a notification indicating the budget has been exceeded (once per Budget_Period per threshold).
5. WHEN a Budget_Period ends, THE Tracker SHALL generate a budget performance report showing actual spending versus the budget limit within 1 hour of the period ending.
6. WHEN a Budget_Period ends, THE Tracker SHALL automatically create a new Budget for the next period with the same limit, allowing the user to adjust the limit before the new period's first transaction is logged.
7. IF the user attempts to create a budget for a category or overall period that already has an active budget, THEN THE Tracker SHALL prevent the duplicate and inform the user that an active budget already exists for that scope.
8. IF the user enters a spending limit that is non-numeric, zero, or negative, THEN THE Tracker SHALL reject the input and display an error message indicating a positive numeric value is required.
9. WHEN displaying budget amounts, THE Tracker SHALL format the spending limit and remaining balance using the Currency symbol, decimal separator, thousands separator, and decimal precision defined by the User_Locale.

### Requirement 9: AI Budget Recommendations

**User Story:** As a user, I want the AI assistant to recommend budgets based on my actual spending history, so that my budgets are realistic and achievable.

#### Acceptance Criteria

1. WHEN the user requests a budget recommendation from the AI_Assistant, THE AI_Assistant SHALL analyze the user's historical income and spending data to generate the recommendation.
2. WHEN the AI_Assistant generates a budget recommendation, THE AI_Assistant SHALL explain the reasoning in plain language, referencing specific data points (category averages, income totals, time periods analyzed) from the user's history.
3. IF the user has fewer than 14 days of transaction history, THEN THE AI_Assistant SHALL inform the user that more data is needed and specify how many more days of logging are required for a reliable recommendation.
4. IF the user has 14 or more days of transaction history, THEN THE AI_Assistant SHALL provide category-level budget recommendations for each category with at least 3 transactions in the analyzed period.
5. WHEN the AI_Assistant provides a budget recommendation, THE AI_Assistant SHALL deliver the response within 15 seconds of the user's request.
6. IF the AI_Assistant is unavailable (LLM API timeout or error), THEN THE Tracker SHALL display an error message indicating the assistant is temporarily unavailable and suggest the user try again later.

### Requirement 10: AI Proactive Budget Coaching

**User Story:** As a user, I want the AI assistant to proactively suggest adjustments when my spending deviates from my budget, so that I can course-correct without having to ask.

#### Acceptance Criteria

1. WHEN the user's actual spending deviates from the pro-rated budget amount (budget limit divided by total days in period, multiplied by days elapsed) by more than 20% at the midpoint of a Budget_Period, THE AI_Assistant SHALL proactively suggest an adjustment to either the budget or spending habits.
2. WHEN the AI_Assistant suggests an adjustment, THE AI_Assistant SHALL explain the reasoning in plain language, referencing the specific deviation amount, the pro-rated expected spend, and historical patterns from previous Budget_Periods.
3. WHEN the AI_Assistant suggests a budget adjustment, THE Tracker SHALL allow the user to accept the adjustment with a single tap or dismiss the suggestion.
4. IF multiple budgets deviate by more than 20% at the midpoint, THEN THE AI_Assistant SHALL generate separate suggestions for each deviating budget, delivered within the same session.
5. WHEN the user dismisses a proactive suggestion, THE AI_Assistant SHALL not re-surface the same suggestion for the same Budget_Period unless the deviation increases by an additional 10 percentage points.

### Requirement 11: AI Conversational Data Queries

**User Story:** As a user, I want to ask the AI assistant questions about my financial data in natural language, so that I can get answers without navigating reports.

#### Acceptance Criteria

1. WHEN the user sends a natural language question about their financial data (amounts, categories, time periods, or trends) to the AI_Assistant, THE AI_Assistant SHALL respond with an answer derived from the user's transaction history.
2. WHEN the AI_Assistant answers a data query, THE AI_Assistant SHALL include the specific numbers and time range used to compute the answer.
3. WHEN the AI_Assistant cannot answer a question due to insufficient data, THE AI_Assistant SHALL state what data is missing and suggest when enough data will be available.
4. WHEN the AI_Assistant provides a response, THE AI_Assistant SHALL complete the response within 10 seconds of the user's query submission.
5. IF the AI_Assistant cannot deliver a response within 10 seconds, THEN THE Tracker SHALL display a timeout message and allow the user to retry the query.
6. IF the user sends a question that is not related to their financial data or cannot be parsed as a data query, THEN THE AI_Assistant SHALL respond indicating the question is out of scope and suggest example questions it can answer.

### Requirement 12: Notification Mechanism

**User Story:** As a user, I want to receive notifications both in-app and via push, so that I stay aware of tasks, alerts, and insights even when the app is closed.

#### Acceptance Criteria

1. THE Tracker SHALL support both in-app notifications and browser push notifications for the following events: Daily_Task reminders, budget threshold alerts, Spending_Spike alerts, periodic summary availability, and AI proactive suggestions.
2. WHEN the user has not completed the Daily_Task by a user-configured reminder time (default: 8:00 PM local time), THE Tracker SHALL send a push notification reminding the user to log (at most one reminder per day).
3. WHEN the user configures notification preferences, THE Tracker SHALL allow the user to enable or disable push notifications independently of in-app notifications.
4. THE Tracker SHALL enable both in-app and push notifications by default upon first use, allowing the user to change preferences at any time.
5. IF the user denies browser push notification permission, THEN THE Tracker SHALL fall back to in-app notifications only and display a message explaining how to re-enable push notifications in browser settings.

### Requirement 13: Data Persistence and Integrity

**User Story:** As a user, I want my financial data to be reliably stored and never lost, so that I can trust the app with my records.

#### Acceptance Criteria

1. WHEN the user saves a transaction, THE Tracker SHALL persist all transaction data (including the ISO 4217 currency code from the User_Locale) to the MySQL database via SQLAlchemy within 5 seconds.
2. IF a database write fails, THEN THE Tracker SHALL retry the write operation up to 3 times with a delay of no more than 2 seconds between each attempt, preserve the user's entered data in the interface, and display an error message indicating the save was unsuccessful if all retries fail.
3. WHEN the user submits a transaction, THE Tracker SHALL validate that the transaction amount is a positive numeric value with decimal places not exceeding the Currency decimal precision defined by the User_Locale before persisting to the database.
4. IF transaction validation fails, THEN THE Tracker SHALL reject the save, highlight the invalid field, and display a message indicating the accepted value constraints for the configured Currency.
5. THE Tracker SHALL store all timestamps in UTC and convert to the user's configured timezone for display.
6. THE Tracker SHALL store all monetary amounts as integers in the smallest currency unit (e.g., cents for USD, yen for JPY) alongside the ISO 4217 currency code to prevent floating-point precision errors.

### Requirement 14: Country and Currency Configuration

**User Story:** As a user, I want the app to be personalized based on my country, so that currency formatting, week start days, and date displays match my local conventions.

#### Acceptance Criteria

1. WHEN the user launches the Tracker for the first time (onboarding), THE Tracker SHALL prompt the user to select their country from a list of supported countries before proceeding to the main interface.
2. WHEN the user selects a country, THE Tracker SHALL determine the default Currency (ISO 4217 code), currency symbol, decimal precision, decimal separator, thousands separator, week start day, and date display format from a predefined locale configuration for that country.
3. WHEN the user has a configured User_Locale, THE Tracker SHALL display all monetary amounts using the Currency symbol, decimal separator, thousands separator, and decimal precision defined by the User_Locale throughout the entire application.
4. WHEN the user has a configured User_Locale with a Currency that uses zero decimal places (e.g., JPY, KRW), THE Tracker SHALL not accept or display fractional amounts for transactions or budgets.
5. WHEN the user has a configured User_Locale with a Currency that uses two decimal places (e.g., USD, EUR), THE Tracker SHALL accept and display amounts with up to two decimal places.
6. WHEN displaying dates, THE Tracker SHALL format dates according to the date display format defined by the User_Locale (e.g., MM/DD/YYYY for US, DD/MM/YYYY for UK, YYYY-MM-DD for ISO locales).
7. WHEN the user navigates to settings, THE Tracker SHALL allow the user to change their country selection, which updates all locale-derived settings (Currency, week start day, date format) immediately.
8. IF the user changes their country in settings, THEN THE Tracker SHALL retain all existing transaction data and display historical amounts using the originally stored Currency code and formatting, while applying the new User_Locale settings to new transactions and UI elements going forward.
9. WHEN a weekly Budget_Period is active, THE Tracker SHALL use the week start day defined by the User_Locale (e.g., Sunday for US, Monday for most European countries) to determine week boundaries.
10. IF the user has not completed onboarding country selection, THEN THE Tracker SHALL not allow access to the main interface until a country is selected.

### Requirement 15: User Profile and Personalization Onboarding

**User Story:** As a user, I want to provide my lifestyle details during onboarding, so that the app can personalize budget categories and weights to match my actual living situation.

#### Acceptance Criteria

1. WHEN the user completes locale onboarding (Requirement 14), THE Tracker SHALL prompt the user to fill in a Lifestyle_Profile questionnaire before granting access to the main dashboard.
2. THE Tracker SHALL capture at minimum: employment/income status (student, working, or both), and commute method (public transit, own vehicle, walking/biking, or none/remote) in the Lifestyle_Profile questionnaire.
3. WHEN the user selects "own vehicle" as commute method, THE Tracker SHALL additionally prompt the user to specify a vehicle type (motorcycle or car).
4. WHEN the user submits the Lifestyle_Profile questionnaire, THE Tracker SHALL store the profile answers on the User record.
5. WHEN the user navigates to Settings, THE Tracker SHALL allow the user to view and edit the Lifestyle_Profile.
6. WHEN the Lifestyle_Profile is created or edited, THE Tracker SHALL trigger a recomputation of the user's Category_Weight set (per Requirement 16).

### Requirement 16: Category Weight Allocation

**User Story:** As a user, I want my budget categories to be weighted based on my lifestyle, so that budget limits reflect my actual needs rather than arbitrary defaults.

#### Acceptance Criteria

1. THE Tracker SHALL maintain a set of Category_Weight entries per user, where each entry represents a percentage allocation for a budget category and all entries for a user sum to exactly 100%.
2. THE Tracker SHALL include at minimum the following categories in the Category_Weight set: Savings, Wants, Transportation, and Food.
3. WHEN a user does not yet have custom Category_Weight entries, THE Tracker SHALL derive a default weight set from the Weight_Rules_Table keyed on the user's Lifestyle_Profile answers (employment status, commute method, and vehicle type).
4. WHEN Category_Weight entries are assigned (default or manual), THE Tracker SHALL retain those entries unchanged until the user explicitly edits their Lifestyle_Profile or manually adjusts a category weight.
5. WHEN the user manually overrides an individual Category_Weight from Settings, THE Tracker SHALL redistribute the remaining categories proportionally so that all weights continue to sum to exactly 100%.
6. THE Tracker SHALL validate that Category_Weight entries sum to exactly 100% before persisting any changes to the database.
7. THE Tracker SHALL store each Category_Weight entry with a flag indicating whether the weight was manually overridden by the user or derived from the Weight_Rules_Table.

### Requirement 17: Dynamic Budget Recalculation on Income Change

**User Story:** As a user, I want my budget limits to automatically adjust when I receive income, so that my budgets always reflect my current available funds.

#### Acceptance Criteria

1. WHEN a transaction is logged with direction = received (income), THE Tracker SHALL recompute each active budget's absolute limit as the corresponding Category_Weight percentage multiplied by the current available balance.
2. WHEN a budget recalculation occurs, THE Tracker SHALL update only the absolute peso amounts (limit_smallest_unit) derived from the Category_Weight percentages — the stored percentage weights SHALL remain unchanged.
3. WHEN a budget's absolute limit changes due to recalculation, THE Tracker SHALL log the change with a reason containing the income amount and source transaction identifier, and surface the change via the existing BudgetCard and notification patterns established in Requirement 8.
4. THE budget recalculation logic SHALL extend the existing BudgetService (task 7.1) — the pro-rated projection and on-track/off-track logic from Requirement 7 SHALL remain unchanged; only the budget limit becomes dynamic instead of static.

### Requirement 18: Unified Personalized Dashboard

**User Story:** As a user, I want a single dashboard that shows my financial picture for any time period with personalized insights, so that I can quickly understand my spending without navigating multiple screens.

#### Acceptance Criteria

1. THE existing HomePage SHALL be extended with a period selector dropdown offering three options: Daily, Weekly, and Monthly.
2. WHEN the user changes the period selector, THE Tracker SHALL display scoped to the selected period: current balance, total income, total expenses, and the per-category budget list with progress indicators.
3. THE dashboard SHALL reuse the existing BudgetCard component and InsightEngine aggregation methods (from Requirement 5) for period-scoped data — the implementation SHALL NOT duplicate aggregation logic already built for periodic summaries.
4. THE dashboard SHALL display one personalization-aware insight at the top, driven by the user's Lifestyle_Profile from Requirement 15 (e.g., a savings-focused tip for users with high Savings weight, or a spending-focused tip for users approaching their Wants limit).
5. THE dashboard visual style SHALL remain consistent with the existing BudgetCard component style — no new design system components SHALL be introduced.
