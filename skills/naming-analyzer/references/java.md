# Java Naming

Source of truth: Google Java Style Guide §5 (Naming) and the Oracle Code
Conventions. Enforced by Checkstyle (`*Name` checks) and Error Prone.

## Conventions

| Kind | Style | Example |
|---|---|---|
| Package | all lowercase, words concatenated, no underscores (Google) | `com.example.deepspace` |
| Class, interface, enum, record, annotation | `UpperCamelCase` nouns | `ImmutableList`, `Readable` |
| Method | `lowerCamelCase`, usually verbs | `sendMessage`, `stop` |
| Field, parameter, local variable | `lowerCamelCase` | `computedValues` |
| Constant | `UPPER_SNAKE_CASE` | `static final int MAX_RETRIES = 3;` |
| Type variable | one capital letter, optionally a digit, or a class-style name + `T` | `T`, `E2`, `RequestT` |
| Test class | class under test + `Test` | `HashIntegrationTest` |
| Getter / setter / predicate (JavaBeans) | `getX` / `setX` / `isX` | `isActive()` |

**Constant means deeply immutable**, not merely `static final`. Google
style lists these as *non*-constants, so `lowerCamelCase` is correct:

```java
static final Logger logger = Logger.getLogger(MyClass.class.getName());
static final Set<String> mutableCollection = new HashSet<>();
static final String[] nonEmptyArray = {"these", "can", "change"};
```

The scanner treats primitives, boxed types, `String`, `BigDecimal`,
`Pattern`, `Duration` and `Immutable*` as constants; other `static final`
fields may be either style.

**Camel case with acronyms (Google):** treat the acronym as a word —
`XmlHttpRequest`, `customerId`, `supportsIpv6OnIos`. The JDK itself is
inconsistent (`HttpURLConnection`), so follow the project.

## File names

A `public` top-level type must live in a file with the same name
(`UserService` → `UserService.java`). The compiler rejects anything else, so
N014 is `major` for Java.

## Common fixes

```java
package com.Example.Users;         → package com.example.users;
class user_store {}                → class UserStore {}
static final int maxSize = 3;      → static final int MAX_SIZE = 3;
private String user_name;          → private String userName;
public void Save_All() {}          → public void saveAll() {}
interface IUserRepository {}       → interface UserRepository {}
```

## Checkstyle

```xml
<module name="TreeWalker">
  <module name="PackageName"><property name="format" value="^[a-z]+(\.[a-z][a-z0-9]*)*$"/></module>
  <module name="TypeName"/>
  <module name="MethodName"/>
  <module name="MemberName"/>
  <module name="ParameterName"/>
  <module name="LocalVariableName"/>
  <!-- ConstantName checks every static final field and cannot see immutability,
       so allow the documented non-constant names explicitly. -->
  <module name="ConstantName">
    <property name="format" value="^([A-Z][A-Z0-9]*(_[A-Z0-9]+)*|log|logger)$"/>
  </module>
  <module name="AbbreviationAsWordInName">
    <property name="allowedAbbreviationLength" value="0"/>
  </module>
</module>
```

Rename with the IDE, or OpenRewrite for many call sites:

```yaml
# rewrite.yml
type: specs.openrewrite.org/v1beta/recipe
name: com.example.RenameSaveAll
recipeList:
  - org.openrewrite.java.ChangeMethodName:
      methodPattern: com.example.UserStore Save_All(..)
      newMethodName: saveAll
```
