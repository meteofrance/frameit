# Troubleshooting code inventory

`CODE_TOPICS` in `src/frameit/utils/diagnostics.py` is the list of public IDs
and chapter slugs. It maps to lower-case fragments in the troubleshooting
pages. Keep the original code/fragment if an entry is retired. Update it to
say which builds emit the code and where to find current help.

| Origin and public surface | Code family | Checks |
|---|---|---|
| `cli` parser/startup, `core.configuration` YAML/schema/template errors; CLI text and JSON reports | `E0001`, `E1001`, `E1101`–`E1107` | `test_v3_cli`, `test_templates`, `test_configuration_v3` |
| `io.loader`, `core.preflight` inventory, selected readers, FA worker transactions; reports, logs and exception causes | `E1002`–`E1008`, `E1201`–`E1207`, `W1001`, `W1201`–`W1203` | `test_v3_reports`, `test_fa_resources`, `test_fa_environment`, `test_fa_epygram_geometry` |
| `processing.requests`, `utils.units`, `processing.wind_reference`, `check.check_functions`; binding, scientific operations, Python warnings and run notices | `E1301`–`E1308`, `E1310`, `W1301`–`W1305` | `test_request_selection`, `test_wind_preflight`, `test_v3_boundary_review`, `test_v3_reports`, `test_logging` |
| `core.preflight` decoded clocks and selection, `core.coupled` association, `core.time_association`; messages and provenance | `E1401`–`E1406`, `W1401`–`W1402` | `test_v3_reports`, `test_nemo_arome_coupling` |
| `tracking`, `processing.extraction`, `processing.tracking.postprocess`, `core.execution`; track and region preparation, completeness, older caller warnings | `E1501`–`E1504`, `W1501`–`W1507` | `test_hpc_execution`, `test_wind_preflight`, `test_v3_boundary_review`, `test_logging` |
| `processing.polar`, `core.settings_class`; sampling, backend, planned limits and older path notices | `E1004`, `E1601`–`E1604`, `W1601`–`W1602` | `test_v3_task16_repairs`, `test_v3_polar`, `test_v3_reports` |
| `core.runtime`, `core.execution`, `core.run_state`, exporters and output paths; log, summary, status/provenance and worker transfer | `E0002`, `E1701`–`E1702`, `E1801`–`E1810`, `W1801` | `test_v3_cli`, `test_hpc_execution`, `test_v3_resources`, `test_zarr_export` |
| `testing.documentation_example`, `testing.datasets`, `testing.matrix`, `testing.all_tests`, published polar qualification/benchmark entry points; command output, backup warning and case records | `E1901`–`E1903`, `W1901`, plus underlying codes when known | `test_task_fixtures`, `test_ci_fixture_location`, `test_matrix_progress`, `test_all_tests`, `test_diagnostic_codes` |
| CLI and run reporting when no more specific cause is available | `E0999` | `test_diagnostic_codes`, `test_v3_cli` |

Check warnings at the source, including `warnings.warn`, direct logging, print
fallbacks, warning lists, worker relays and `record_notes`. The scoped warning
hook can also transport third-party text; it does not make it a FrameIt
warning. `W1203` labels FrameIt's existing FA worker notice, not the raw
decoder text kept in its records. A shell or scheduler failure, a fatal
process exit, an expected optional capability probe, or a normal deferred
check has no code of its own.

`testing.fa_epygram_probe` is a maintainer-only FA comparison tool, not the
user's reader; its command usage errors are not part of the public catalogue.
`example/slurm/check_run.py` checks already written products with ordinary
readers, independently of FrameIt. Its findings, plot script assertions,
and shell example messages do not come from FrameIt processing.

Check internal raises by following their callers. Preserve a code from
the closest owner that knows the cause. At an input, method, or output
boundary, a known rejection gets the code for that boundary; unhandled and
opaque failures use `E0999` without guessing from another library's message.
Do not classify test assertions, debug messages, or private experiment scripts
as supported user diagnostics. No code changes a check, calculation, fallback,
or completion decision.

For a new code add the explicit entry, its index link, and a test at a user
boundary. The publication checker checks all registered code links and old
hub bookmarks in the built site. It does not certify scientific methods or
prove that an unexercised external failure can be detected.
