# DeepSeek heldout real-project comparison

This is actual main-model candidate generation, real Jev inference, native Memory application/use and Harness execution. It is not evidence of a net quality gain.

Main selection: `cli-proxy/opencode/deepseek-v4.1-flash`. The bounded readiness response returned `deepseek-v4.1-flash`. Jev responses reported `jev-1.13.0`; SDK remains pinned to 0.6.0. Experimental composed policy was explicitly selected; production default was not activated.

| Observed outcome | Jev off | Jev on |
| --- | ---: | ---: |
| Project acceptance | 3/3 | 2/3 |
| Expected Memory items written | 6/6 | 5/6 |
| Harness native probes passed | 3/3 | 3/3 |
| Learning seconds, summed | 474.67 | 928.79 |
| Known learning cost estimate, USD | 0.115457712 | 0.154381752 |

The only failed arm is yocto-queue-on: the private preference was applied independently, but the supported project verification command was held because its description counterevidence judgment was uncertain. Recall for that arm is unverified, rather than failed or free. The 16 frozen entries contain no tool error flags and contain successful tests at indexes 8 and 12; a transient-failure explanation is not established. Raw Jev answer probabilities were not retained, so the uncertainty cause cannot be reconstructed from the receipt alone.

There were 200 total transport requests: 171 main-model requests and 29 Jev requests, with no proxy-recorded errors. Jev returned usage for all 29 responses: 190962 input and 3364 output tokens. At the current [official input price](https://docs.typesafe.ai/models), its estimated cost is USD 0.008020404. Main pricing is configured metadata. Invoiced billing is not verified; receipt availability flags are false and recorded totals are known estimates only.

Independent read-only review verified the source/image/report identities, six meaningful added regressions, eleven written Memory items and six Harness rules. No mistaken Memory or extra generalization was observed in these positive scenarios. Harness rules did not expand the original no-push requirement, but single probes do not cover every shell spelling or establish a false-block rate. All six owned containers are absent.

The baseline shares the project and filesystem; every executed baseline manually discovered the saved preference. Baseline/fresh differences measure this bounded discovery/use path, not a clean no-Memory counterfactual. Off/on arms independently generated their candidates; differing repairs and generation make the total cost/time difference unsuitable as a causal Jev overhead estimate. Direct reported Jev judgment durations sum to 18.329 seconds.

The cohort has positive durable requirements, not a dedicated adversarial negative set. It cannot establish reduced mistaken learning for speculation, temporary failures, conflicts or unauthorized constraints. Preserve the historical negative experiments and these new negatives. No threshold or label was changed to obtain a pass.

For diagnosing this run, read @packages/continual-learning/tests/deepseek-heldout-comparison-results.json and the raw directory it names. Before any next policy change, evaluate the uncertain description check on fixed bilingual positive and negative samples, preserve full original evidence and permissions, and retain unknown/service failures as proposals or the existing fallback. Do not interpret this next step as a verified improvement.

Verification for the model-selection change: RED 2 failed/4 passed; focused 18 passed; continual-learning 1045 passed in 436.93 seconds; root TypeScript passed; 19 packed workspace manifests and target dry pack passed; package diff check passed. Installation check remains exit 1 due to eleven unrelated unconfigured packages; continual-learning is present.
