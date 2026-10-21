# Desktop OSC v0.8.22-prebuild.8

Addresses repeated installer failures during `extract`, including the October 21 v0.8.22-prebuild.7 timeout. Moves extraction to streamed .NET ZIP reads, with size limits, path traversal rejection, per-file heartbeat checkpoints, a single-instance installer mutex and unique staging. The Desktop ZIP must be installed manually once because older versions contain the defective extractor. Combat and the VPS are unchanged. This is a code fix awaiting live Windows validation.
