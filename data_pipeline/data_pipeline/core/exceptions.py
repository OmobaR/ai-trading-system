"""Custom exceptions for pipeline failures."""


class PipelineError(Exception):
    """Base pipeline exception."""
    pass


class ValidationError(PipelineError):
    """Data validation failure."""
    pass


class AlignmentError(PipelineError):
    """Time alignment failure."""
    pass


class IngestionError(PipelineError):
    """Data ingestion failure."""
    pass


class IntegrityError(PipelineError):
    """Data integrity violation."""
    pass


class DataContaminationError(PipelineError):
    """Mixed timeframe contamination detected."""
    pass
