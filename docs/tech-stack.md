# Tech Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Language | Python 3.14 | Locked |
| Validation / models | Pydantic V2 | Locked — single source of truth |
| AI harness | Pydantic AI | Locked |
| API | FastAPI | Locked |
| Frontend | React + TypeScript + Vite | Locked |
| Local runtime | Docker + Docker Compose | Locked |
| Python packaging | UV (workspaces if multiple packages) | Locked preference |
| MIDI writing | Deterministic library (e.g. mido) behind an interface | Suggestion — keep binary format out of the LLM |

Versions are pinned at scaffold time; lockfiles become authoritative.

## Dependency rules

- Only very open licenses: MIT, Apache 2.0, or clear equivalents. No AGPL or strong copyleft.
- Prefer well-maintained existing libraries over custom implementations.
- Thin wrappers around libraries are acceptable; large "shoehorn" adapters are not.
- Most third-party libraries should sit behind interfaces/protocols so they can be swapped or mocked. Core, stable libraries may be used directly when the cost of abstraction is higher than the benefit.
