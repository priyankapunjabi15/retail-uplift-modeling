# retail-uplift-modeling

Causal uplift modeling on retail promotion data from MySQL schema through a deployed FastAPI + Streamlit scoring app.



End-to-end causal uplift modeling pipeline on the Kevin Hillstrom MineThatData

email dataset — estimating the incremental effect of a promotional email per

customer (not just predicting who'll buy), segmenting customers into

Persuadables / Sure Things / Lost Causes / Sleeping Dogs, and deploying the

result as a scored API + dashboard.



\## Status

In progress — see commit history for pipeline stage.



\## Stack

Python, MySQL, scikit-learn, LightGBM, PyTorch, causalml/econml, FastAPI, Streamlit



\## Why uplift modeling, not propensity modeling?

A propensity model predicts who will buy. It can't distinguish a customer

who buys because of the discount from one who'd buy anyway. Uplift modeling

estimates the causal incremental effect of the promotion per customer — the

number that actually justifies spending money on it.

