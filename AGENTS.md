# FrameIt — Development instructions for coding agents

> Automate repetitive work. Make scientific choices explicit. Harmonize data without erasing its meaning. Preserve researchers' freedom.

## 1. Mission and scope

FrameIt is a configurable Python tool for repeatable scientific post-processing. Its purpose is to reduce the technical work between simulation outputs and scientific analysis, share reusable methods across researchers and projects, and produce data that colleagues can understand, compare, and reuse.

Develop FrameIt as a **focused, interoperable processing tool**, not an all-in-one scientific suite. Cyclone workflows are a starting point, not a justification for hard-coding cyclone assumptions into every component.

These instructions define development policy, not a catalogue of implemented or scientifically validated features. Verify capabilities against the current working tree. Do not treat a roadmap, an old release archive, or a proposed output format as evidence of current support.

Use **MUST** for requirements and **SHOULD** for preferred practices. Apply these instructions within the agent's governing permissions and the maintainer-approved task. Surface conflicts instead of silently weakening scientific safeguards or expanding scope. Do not turn every policy gap into an unsolicited refactor.

## 2. Non-negotiable boundaries

- **No all-in-one application.** Do not accumulate every diagnostic, plot, interface, workflow manager, or analysis feature until FrameIt becomes difficult to install, understand, or use. Prefer a small core and integration with existing tools.
- **No black box.** Scientific assumptions, transformations, defaults, fallback decisions, and limitations MUST be inspectable and reproducible.
- **No replacement for scientific judgment.** A completed run, passing tests, or a visually plausible result MUST NOT be presented as proof of scientific validity.
- **No compulsory research workflow.** FrameIt MUST leave researchers free to use their own scripts, methods, and downstream tools. Do not impose a FrameIt-specific analysis environment.
- **No unvalidated stable diagnostics.** Stable built-in diagnostics MUST use established, peer-reviewed methods with demonstrated use in the relevant scientific community and a validated implementation.
- **No mandatory diagnostics.** Core extraction, harmonization, and export MUST remain usable without executing optional diagnostics or installing their unrelated dependencies.
- **No format lock-in.** Scientific outputs MUST remain usable through ordinary readers for the supported NetCDF/Zarr format, without requiring FrameIt to interpret the basic data model.
- **No harmonization that hides physics.** Preserve meaningful distinctions between variables, grids, models, sampling conventions, and reference frames.
- **No dependence on one person's private setup.** Keep code, tests, documentation, and examples understandable and portable. Do not embed personal paths, credentials, or undocumented local services.

## 3. Start from the repository, not assumptions

Before editing, inspect the task-relevant parts of the current repository:

1. Read applicable repository instructions, the README, contribution guidance, and any approved design decisions relevant to the task.
2. Check the working tree and existing changes. Identify the actual implementation, configuration schema, tests, packaging, and CI commands involved.
3. Establish expected behavior and the smallest useful acceptance test. For a bug, reproduce it with a minimal case when feasible.
4. Identify scientific, output-schema, compatibility, dependency, and resource implications before choosing an implementation.

Do not invent module names, supported models, CLI flags, configuration keys, Python versions, test commands, or validation results. Discover them locally. Read narrowly enough to avoid repeatedly loading unrelated datasets or documents.

Preserve unrelated work. Do not rewrite history, reset changes, upgrade the whole environment, or restructure the repository merely to complete a focused task. Routine reversible implementation choices do not need repeated approval; unresolved scientific choices and changes to agreed scope do.

## 4. Feature admission and architecture

Before adding a feature, answer: **Which demonstrated user task does this simplify, and why does it belong in FrameIt rather than a downstream script or existing tool?**

Prefer, in order: reuse an existing capability; make a small extension; integrate an established library behind a narrow interface; introduce a new component only when justified. Do not create a generic plugin system, abstraction hierarchy, or new service solely for hypothetical future use.

Keep logical boundaries between input adapters, configuration, scientific transformations, optional diagnostics, output writers, and user interfaces. Reuse the current architecture where possible; these boundaries are not an instruction to rewrite it.

Scientific calculations MUST NOT depend on a GUI, terminal wizard, plotting system, or particular downstream viewer. Model-specific conventions belong in adapters or explicitly identified methods, not scattered throughout generic processing code. Optional dependencies SHOULD be loaded only on the paths that require them.

A narrowly specialized method may be valuable in a research script without belonging in the shared core. Generalize from demonstrated needs, not speculative completeness.

## 5. Automate execution, not hidden scientific decisions

Automation is encouraged when it executes a declared, reproducible plan. Examples include input inventory, metadata checks, repeated extraction, batch scheduling within approved resource limits, and output bookkeeping.

Scientific decisions require a different standard. Method selection, variable interpretation, unit conversion, interpolation, masks, reference frames, aggregation, thresholds, extrapolation, and missing-data policy MUST be explicit in configuration or represented by documented, inspectable defaults.

- Separate discovery from selection: finding several candidate fields or methods does not establish which one is scientifically appropriate.
- Resolve defaults into a record of the effective configuration. User overrides MUST have a documented precedence.
- Do not infer units, variable identity, or scientific meaning from a filename alone when the evidence is ambiguous.
- A fallback MUST be declared, scientifically justified, reported, and recorded. Never silently substitute a different physical quantity, method, time, or coordinate convention.
- Invalid required inputs or unresolved scientific ambiguity MUST produce an actionable failure for the affected operation. Optional failures may allow other work to finish only under a documented policy that clearly marks incomplete outputs.
- Never turn missing values into physical zeroes, fill gaps, clip values, smooth fields, or extrapolate merely to make a result look complete.

A batch workflow should not require interactive confirmation for every case. Establish the policy beforehand, then apply it consistently and record exceptions. User-visible behavior SHOULD remain explainable without reading the implementation.

## 6. Scientific diagnostics: admission and validation

### Stable methods only in the supported diagnostic catalogue

A stable built-in diagnostic MUST satisfy all of the following:

1. **Scientific basis:** a verifiable peer-reviewed publication supports the actual method implemented, including its relevant assumptions and definitions.
2. **Community use:** there is concrete evidence of established use in the relevant field, not merely an assertion that the method is popular.
3. **Implementation specification:** equations, inputs, units, constants, discretization, conventions, and departures from the reference are documented.
4. **Independent verification:** tests compare against analytically known results, independent calculations, or a trusted reference implementation or dataset with justified tolerances.
5. **Applicable scope:** valid regimes, sensitivity, known failure modes, and limitations are documented and reviewed before promotion to stable status.

A citation alone does not validate an implementation. Agreement with an old FrameIt output is a regression check, not independent scientific verification. Agreement with a reference implementation is not, by itself, proof of validity for every dataset or regime.

Verify references against the publication itself or an authoritative publisher record. Never fabricate a DOI, reference result, or evidence of community adoption. Blogs, preprints, generated text, and software documentation alone do not satisfy the stable-method publication requirement. When evidence cannot be checked, state what is missing and leave the scientific claim unresolved.

Apply scientific verification to core numerical transformations as well as named diagnostics. Ordinary file handling does not need a peer-reviewed citation for every line of code.

### Optional and proportionate

Compute diagnostics only when explicitly selected by the user or by a clearly documented, user-selected preset. Do not compute everything just because its inputs are available. Necessary internal calculations may still run, but their purpose and cost must be clear.

Enabling a diagnostic MUST NOT silently alter unrelated base variables, coordinates, or sampling. A diagnostic SHOULD declare its required inputs, output definition, applicability, dependencies, and material resource cost before execution.

Novel or unusually specialized research methods should normally remain in personal scripts or external extensions. An explicitly requested experimental implementation requires maintainer approval, clear experimental labeling, and separation from stable defaults. It MUST NOT bypass the admission criteria by being described as validated.

### Record for a new or materially changed method

Keep a concise method record in the repository's existing documentation structure:

```text
Quantity, method name, and maturity status:
Primary reference and evidence of relevant community use:
Required inputs, units, grids, and sampling conventions:
Equations, constants, parameters, and numerical choices:
Differences from the published/reference implementation:
Applicability, exclusions, sensitivity, and failure behavior:
Independent verification cases and justified tolerances:
Output metadata and provenance:
Remaining validation gaps and review status:
```

An agent MUST NOT invent human approval or promote its own review into independent scientific sign-off. Undocumented existing methods are validation debt, not permission to make stronger claims or remove functionality without approval.

## 7. Harmonization, interoperability, and personal scripts

Treat the output data contract as a public interface. For every supported output, make variable definitions, dimensions, coordinates, units, missing values, time conventions, and relevant processing metadata understandable outside FrameIt.

NetCDF/Zarr output is intended to let researchers keep their existing tools. **Do not promise that every script will work unchanged merely because the file format matches.** Compatibility also requires matching schemas, physical definitions, dimension conventions, and reader support. Preserve compatible schemas where possible and document necessary adaptations.

For a writer or schema change:

- Verify which formats, versions, encodings, and readers the repository actually supports. Do not advertise planned support as implemented.
- Reopen the output with an ordinary independent reader appropriate to the format, without importing FrameIt, and check both values and metadata.
- Document chunking, compression, precision, and special reader requirements. Do not make one downstream application's storage preferences the universal contract.
- Keep the stable schema explicit. Treat incompatible renaming, reordering, units, masks, reference frames, defaults, or encoding changes as compatibility changes requiring review and migration guidance.

Follow the project's chosen scientific metadata conventions. Use standard names only when the quantity really matches their definition. Record actual conversions and transformations; changing a label is not harmonization.

Preserve distinctions such as instantaneous versus accumulated or averaged fields, grid-relative versus Earth-relative vectors, vertical coordinate definitions, and different model representations of a similarly named quantity. When equivalence cannot be established, retain the distinction and explain it.

Sharing outputs SHOULD not require access to a developer's home directory. Preserve useful provenance without publishing credentials, private host details, or unnecessarily identifying absolute paths.

## 8. Numerical correctness and provenance

For affected scientific operations, verify dimensional consistency, axis order, masks, boundary handling, temporal interpretation, coordinate orientation, and interpolation behavior. Do not assume all inputs use the same model grid or conventions.

For coordinate or vector work, distinguish sampling locations, vector basis rotation, and reference-frame motion. Rotating a displayed domain is not permission to silently change the meaning of wind components. Explicitly test the conventions actually implemented.

For regridding and aggregation, choose tests appropriate to the quantity and method: conservation where promised, treatment of intensive versus extensive quantities, weighting, and valid-data coverage. Do not claim conservation for a method that does not provide it.

Outputs or a portable associated manifest MUST record enough information to explain how they were produced: relevant source identifiers, FrameIt version and code revision when available, effective configuration, methods and parameters, coordinate and unit transformations, processing history, and significant warnings or incomplete steps. Capture dependency versions when they affect the numerical result.

Use the existing provenance mechanism where possible. Do not claim input identity was verified without the required evidence; distinguish paths, metadata fingerprints, and content checksums. Avoid unnecessary full-archive hashing when a cheaper declared strategy meets the workflow's needs.

Scientific reproducibility, numerical agreement within a justified tolerance, and bitwise identity are different acceptance criteria. State which one was tested.

## 9. Testing and performance

Use the project's existing tools and conventions. Add or update the smallest tests that exercise the changed behavior; a documentation-only edit does not require an unrelated scientific benchmark.

For applicable code changes, cover:

- **Behavior and failure:** ordinary cases, missing or ambiguous inputs, invalid configuration, and documented error handling.
- **Scientific correctness:** known solutions or independent references, edge cases, tolerances, and relevant physical or numerical properties.
- **Integration and compatibility:** a small end-to-end processing case, output reopening, metadata, and established user-facing behavior.
- **Optionality:** base processing with diagnostics disabled; requested diagnostics with required dependencies present and missing.

Use compact synthetic fixtures where possible and representative real data when needed to establish applicability. Synthetic tests alone MUST NOT be described as validation of all real-world conditions. Do not rely exclusively on plots, snapshots, or golden files, and do not update expected results solely to make tests pass.

Preserve the numerical contract when optimizing. Measure relevant wall time, memory, and I/O against a baseline; document the workload and environment. Do not introduce precision loss, new approximations, aggressive parallelism, or a heavy dependency without explaining the trade-off.

For large datasets, prefer bounded-memory processing and avoid unnecessary full-array loading or copies. Cap concurrency and avoid worker/thread oversubscription. Resource-aware design is expected; a new distributed execution framework is not automatically justified.

## 10. Safe execution and maintainability

Treat source datasets as read-only unless explicitly instructed otherwise. Write outputs to designated locations, prevent accidental overwrites, and distinguish partial products from successful products. Use atomic finalization or an appropriate completion protocol where supported.

Do not launch expensive production runs, large downloads, external uploads, or shared-cluster jobs without authorization for their resource and data implications. Use small fixtures first. Never commit credentials, private datasets, generated bulk outputs, or machine-specific environment state.

Keep interfaces small, dependencies justified, and errors actionable. Follow existing formatting and type conventions. Comments and docstrings should explain scientific meaning, invariants, and non-obvious choices rather than narrate routine syntax.

Documentation MUST distinguish implemented capabilities, planned work, experimental features, and unresolved validation. Update configuration examples, scientific method notes, output descriptions, and migration guidance when the change affects them. Preserve attribution and license requirements for reused methods and code.

## 11. Completion and handover

Before marking work complete, review the diff and verify:

- [ ] The requested problem is addressed without unrelated features or rewrites.
- [ ] Scientific assumptions, defaults, failure modes, and remaining uncertainties are explicit.
- [ ] Diagnostics remain optional and any stable-method claims have supporting evidence.
- [ ] Output semantics and compatibility are preserved, or changes have explicit approval and migration guidance.
- [ ] Relevant tests were run; unavailable checks are identified rather than claimed as passed.
- [ ] Documentation and provenance reflect the changed behavior.
- [ ] No source data, unrelated work, or private material was damaged or exposed.

Use a short final handover:

```text
Changed: what was implemented and where.
Scientific impact: method, assumptions, defaults, or none.
Compatibility: output/configuration changes and migration, or none.
Verification: exact commands executed and observed results.
Limitations: tests not run, unresolved evidence, and required review.
```

When delegating, give each agent a bounded task, relevant interfaces, these safeguards, and explicit verification expectations. Do not let multiple agents independently redefine shared scientific defaults or output schemas. Review their combined changes before declaring the task complete.

**The measure of success is less repeated work, trustworthy and reusable data, and a maintainable tool—not the number of features added.**
