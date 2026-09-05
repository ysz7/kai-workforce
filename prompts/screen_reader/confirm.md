You are looking at a screenshot of a real screen, taken immediately after an
action was performed on it. Decide whether the expected result is actually
there.

The image is {width} pixels wide and {height} pixels high.

# What was expected

{expectation}

# Your answer

Return JSON and nothing else:

```json
{{
  "answer": "what the screen shows now, in one or two sentences",
  "confirmed": false,
  "targets": []
}}
```

# Rules

- `confirmed` is true only if you can see the expected result. Not if the screen
  looks like it is on the way there, and not if it is plausible.
- When it is false, `answer` says what is on the screen instead. That is what
  the next decision is made from.
- A screen that is still loading is not a confirmation. Say that it is loading.
- Include a target only if there is something the next action would need to
  reach.
