FROM python:3.12
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . || pip install --no-cache-dir euroleague-api==0.1.1 duckdb polars pandas pyarrow scikit-learn statsmodels pymc arviz streamlit plotly altair matplotlib
COPY . .
RUN pip install --no-cache-dir -e .
CMD ["python", "-c", "print('elrapm container ready')"]
