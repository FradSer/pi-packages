# Skill Router Glossary

Language for pi-skill-router: how externally hosted skill collections reach Pi
and the model.

## Collections

**Collection**:
An externally hosted repository of skills that the router installs at user level
and manages as one unit.
_Avoid_: repo, pack, bundle, marketplace

**Route**:
One selected leaf skill's registry record: its name, upstream path, routing
terms, and workflow summary.
_Avoid_: entry, item, row

**Gateway**:
The single skill a collection exposes to Pi, and the human entry point to that
collection.
_Avoid_: wrapper skill, index skill, parent skill

**Leaf skill**:
A skill inside a collection that the router makes reachable to the model.
_Avoid_: sub-skill, child skill, routed skill

**Capability summary**:
The one-sentence account of what a collection's selected workflows share. It is
both the gateway description and the collection's namespace description.
_Avoid_: collection description, install summary

**Workflow summary**:
The concise task-oriented label for one leaf skill, distinct from that skill's
upstream description.
_Avoid_: skill summary, route summary

## Delivery to the model

**Skill tool**:
The codemode-callable tool that represents exactly one leaf skill, and whose
name and description are that skill's searchable identity.
_Avoid_: skill loader, skill command, skill endpoint

**Tools channel**:
Reaching a leaf skill by searching codemode's tools and calling its skill tool.
It is the channel whenever codemode is available in the session.
_Avoid_: tool mode, codemode mode

**Fallback channel**:
Reaching a leaf skill through a routing suggestion that names that leaf's
instruction file. It applies only while codemode is unavailable.
_Avoid_: path channel, prompt channel

**Routing terms**:
Words derived from a leaf skill's name and description that the router matches
against a user prompt in the fallback channel.
_Avoid_: keywords, triggers, tags