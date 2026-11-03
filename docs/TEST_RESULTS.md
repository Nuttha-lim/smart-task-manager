# Test and build results

Checked on 3 November 2026 on Windows.

| Check | Environment | Result |
| --- | --- | --- |
| Backend tests | Python 3.14, SQLite in memory, mocked AI responses | 268 passed |
| Flutter tests | Flutter 3.44.8, Dart 3.12.2 | 7 passed |
| Release web build | Flutter 3.44.8 | Passed |

The backend tests cover task operations, planning, calendars, notifications, rewards and file handling. They use temporary databases and mock external AI responses. Live Groq responses, PostgreSQL integration and push delivery require separate integration checks.

The supplied tests needed a fixed date for a timetable-cancellation case, mocked AI responses for two chat cases, and the current chat screen in the Flutter startup test. The backend run reported deprecation warnings, mainly from existing datetime and framework usage. Application code was preserved.
