# Backend image (P10-03). Build context: backend/. Compose passes `eval/` as the named context
# `pins` so the NLP library pins are shared with the eval-nlp CI job.
#   --build-arg WITH_NLP=0  -> slim image, rule-only NLP (no spaCy / embeddings)
# Base pinned by digest (python:3.11-slim as of 2026-10-08). Bump it deliberately: a new digest
# invalidates every layer below, including the multi-GB torch install.
FROM python:3.11-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce

# Default on: the demo (P10-04) shows categorized, entity-aware explanations, which need the
# models. The rules alone still classify amount/date/obligation changes (06_NLP_SPEC).
ARG WITH_NLP=1
# Model weights, pinned exactly (same values as .github/workflows/eval-nlp.yml).
ARG SPACY_MODEL_URL=https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
ARG SPACY_MODEL_SHA256=1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85
ARG HF_MODEL_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

WORKDIR /app
COPY --from=pins nlp-pins.txt /pins/nlp-pins.txt
COPY pyproject.toml ./
# Empty stub packages so the first `pip install .` resolves and installs only the dependencies;
# the real source is copied after the heavy layers (see the end of the install block).
RUN mkdir app proofchain_core && touch app/__init__.py proofchain_core/__init__.py
ENV SPACY_MODEL_URL=$SPACY_MODEL_URL SPACY_MODEL_SHA256=$SPACY_MODEL_SHA256     HF_MODEL_REVISION=$HF_MODEL_REVISION
COPY nlp_fetch_models.py /tmp/nlp_fetch_models.py

RUN pip install .
# Separate layers so a model tweak does not redo the multi-GB torch install.
RUN if [ "$WITH_NLP" = "1" ]; then       pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu; fi
RUN if [ "$WITH_NLP" = "1" ]; then pip install -c /pins/nlp-pins.txt ".[nlp]"; fi
RUN if [ "$WITH_NLP" = "1" ]; then python /tmp/nlp_fetch_models.py && chmod -R a+rX /opt/hf; fi
RUN rm /tmp/nlp_fetch_models.py

# Source last: an edit under app/ or proofchain_core/ rebuilds only these two small layers.
COPY proofchain_core ./proofchain_core
COPY app ./app
RUN pip install --force-reinstall --no-deps .

RUN useradd --system --uid 10001 --no-create-home proofchain
USER proofchain
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=10s --start-period=90s --retries=3 \
  CMD ["python", "-m", "app.scripts.healthcheck"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
