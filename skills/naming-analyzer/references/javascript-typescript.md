# JavaScript and TypeScript Naming

No single official guide; these are the conventions shared by the TypeScript
handbook, MDN, and the major style guides. Enforced by ESLint `camelcase` and
`@typescript-eslint/naming-convention`. **Project config beats everything
here** — JS codebases vary more than most.

## Conventions

| Kind | Style | Example |
|---|---|---|
| Variable, function, parameter, method, property | `camelCase` | `fetchUser`, `retryCount` |
| Class, interface, type alias, enum | `PascalCase` | `UserService`, `type UserId = string` |
| Enum member | `PascalCase` (TS handbook) | `Direction.Up` |
| True constant (module-level, primitive, never reassigned) | `UPPER_SNAKE_CASE` | `const MAX_RETRIES = 3` |
| Other `const` bindings | `camelCase` | `const user = await fetchUser()` |
| React component (`.jsx`/`.tsx`) | `PascalCase` — required for JSX to treat it as a component | `function UserCard()` |
| React hook | `use` + `PascalCase` — required by the Rules of Hooks lint | `useUserProfile` |
| Private class member | `#field` (real privacy) or `_field` (convention) | `#cache` |
| Boolean | `is` / `has` / `can` / `should` prefix | `isOpen`, `hasError` |
| Event handler / prop | `handleX` inside, `onX` as the prop | `<Button onClick={handleSave}>` |
| File | match the project: `kebab-case.ts` or `PascalCase.tsx` for components | `user-service.ts` |

Acronyms: both `HttpClient` (Angular, TypeScript compiler guidelines) and
`XMLHttpRequest` (DOM) exist. Pick one per project; the scanner does not
enforce either.

**Interfaces without `I`.** The TypeScript coding guidelines say not to
prefix interface names with `I` (`IUser` → `User`). Reported as N005 `info`.

## Idioms the scanner accepts

- `$` prefixes (`$el`, jQuery/Svelte stores) and `_` prefixes.
- `PascalCase` for `const` bindings (schemas, enum-like objects, class
  aliases) and for `require()`/`import()` results (`const Parser = require('./parser')`).
- `i j k n x y z e` single letters; loop variables of any length.
- `.d.ts`, `*.min.js` and bundled files (lines over 1000 chars) are skipped.

## Common fixes

```typescript
function get_user(user_id) {}            → function getUser(userId) {}
class userStore {}                       → class UserStore {}
interface IUser {}                       → interface User {}
let loading = true;                      // fine: state adjective
let status = false;                      → let isActive = false;
const fetch_all = async () => {};        → const fetchAll = async () => {};
type user_id = string;                   → type UserId = string;
```

## ESLint setup (flat config)

```javascript
// eslint.config.js — ESLint 9.22+ and typescript-eslint 8
import { defineConfig } from "eslint/config";
import tseslint from "typescript-eslint";

export default defineConfig({
  files: ["**/*.ts", "**/*.tsx"],
  extends: [tseslint.configs.base],
  // The `types` selector below needs type information.
  languageOptions: { parserOptions: { projectService: true } },
  rules: {
    "@typescript-eslint/naming-convention": [
      "error",
      { selector: "default", format: ["camelCase"], leadingUnderscore: "allow" },
      { selector: "variable", modifiers: ["const"], format: ["camelCase", "UPPER_CASE", "PascalCase"] },
      { selector: "typeLike", format: ["PascalCase"] },
      { selector: "enumMember", format: ["PascalCase"] },
      { selector: "variable", types: ["boolean"], format: ["PascalCase"],
        prefix: ["is", "has", "can", "should", "was", "did"] },
      { selector: "objectLiteralProperty", format: null },  // external payloads
    ],
  },
});
```

Rename with the editor's tsserver "Rename Symbol", or script it with
ts-morph, which updates every reference in the project:

```typescript
// scripts/rename.ts — run with: npx tsx scripts/rename.ts
import { Project } from "ts-morph";

const project = new Project({ tsConfigFilePath: "tsconfig.json" });
project.getSourceFileOrThrow("src/user.ts").getFunctionOrThrow("get_user").rename("getUser");
await project.save();
```
