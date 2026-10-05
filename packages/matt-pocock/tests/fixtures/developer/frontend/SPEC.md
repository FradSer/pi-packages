# frontend

Render a labelled text input from renderField(label,value,id). The provided id is a trusted unique identifier. Associate label for with input id, use type="text", and HTML-escape label text and the double-quoted value attribute (including ampersand, angle brackets and quote). Preserve Unicode. No scripts, frameworks, dependency or network. This task validates generated HTML, not browser layout or screen-reader behavior.
Given user text includes markup or quotes, when rendered, then it stays text. Given an id, then the label and input are programmatically associated.

The module exports only renderField; helpers stay private.
