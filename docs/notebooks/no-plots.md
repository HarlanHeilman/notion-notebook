> Notebook Metadata
> 
> Last Sync: 2026-04-30 21:14:40 UTC
> GitHub Remote: git@github.com:HarlanHeilman/notion-notebook.git
> Notebook Path: notebooks/demo-local/no-plots.ipynb

[notion-notebook] EXPORT_REGION_BEGIN v1

## Notebook export (no-plots.ipynb)

---

```python
from notion_notebook import LocalNotebookExporter

exporter = LocalNotebookExporter(
    notebook_output_dir="../../docs/notebooks",
    figure_output_dir="../../docs/figures",
)
exporter.start()
```

Synthetic datasets with descriptive summaries, correlations, group comparisons, and contingency-table inference. No figures; outputs are tables and scalar statistics only.

```python
import numpy as np
import pandas as pd
from IPython.display import display
from scipy import stats

rng = np.random.default_rng(42)

n_daily = 120
daily = pd.DataFrame(
    {
        "revenue_usd": rng.lognormal(mean=6.0, sigma=0.35, size=n_daily),
        "units_sold": rng.poisson(lam=42, size=n_daily),
        "refund_rate": rng.beta(a=2, b=18, size=n_daily),
        "day_index": np.arange(n_daily, dtype=np.int64),
    }
)
daily["revenue_usd"] = daily["revenue_usd"].round(2)
daily.head()
```

   revenue_usd  units_sold  refund_rate  day_index
0       448.83          31     0.051512          0
1       280.34          39     0.043142          1
2       524.61          32     0.126419          2
3       560.71          43     0.129444          3
4       203.80          44     0.125959          4

```python
n_a, n_b = 80, 75
scores_a = rng.normal(loc=100.0, scale=12.0, size=n_a)
scores_b = rng.normal(loc=108.0, scale=14.0, size=n_b)
ab_test = pd.DataFrame(
    {
        "score": np.concatenate([scores_a, scores_b]),
        "variant": np.array(["A"] * n_a + ["B"] * n_b, dtype=object),
    }
)
ab_test.head()
```

        score variant
0   91.677926       A
1  109.972382       A
2   83.893898       A
3   95.116675       A
4   92.981510       A

```python
n_cust = 200
regions = rng.choice(
    ["North", "South", "East", "West"],
    size=n_cust,
    p=[0.25, 0.25, 0.25, 0.25],
)
plans = rng.choice(
    ["Basic", "Pro", "Enterprise"],
    size=n_cust,
    p=[0.5, 0.35, 0.15],
)
base_churn = {"Basic": 0.22, "Pro": 0.14, "Enterprise": 0.09}
churn_prob = np.array([base_churn[p] for p in plans])
churned = rng.binomial(1, churn_prob)
customers = pd.DataFrame(
    {
        "region": regions,
        "plan": plans,
        "churned": churned,
    }
)

customers.head()
```

  region        plan  churned
0  South       Basic        0
1   East  Enterprise        0
2   West         Pro        0
3  North         Pro        0
4   East         Pro        1

## Daily operations panel

Lognormal revenue, Poisson units, and Beta-distributed refund rates over 120 synthetic days.

```python
numeric_cols = ["revenue_usd", "units_sold", "refund_rate"]
daily_summary = daily[numeric_cols].describe()
daily_corr = daily[numeric_cols].corr(method="pearson")
skew_kurt = pd.DataFrame(
    {
        "skew": daily[numeric_cols].skew(),
        "kurtosis_excess": daily[numeric_cols].kurtosis(),
    }
)
display(daily_summary)
display(daily_corr)
display(skew_kurt)
```

       revenue_usd  units_sold  refund_rate
count   120.000000  120.000000   120.000000
mean    409.906667   41.966667     0.093946
std     112.895787    6.998119     0.064738
min     203.800000   26.000000     0.007894
25%     333.305000   37.000000     0.048268
50%     398.750000   42.000000     0.083623
75%     481.595000   47.250000     0.126074
max     853.700000   58.000000     0.403743

             revenue_usd  units_sold  refund_rate
revenue_usd     1.000000   -0.094566    -0.078450
units_sold     -0.094566    1.000000     0.252055
refund_rate    -0.078450    0.252055     1.000000

                 skew  kurtosis_excess
revenue_usd  0.712451         1.118434
units_sold   0.014283        -0.530850
refund_rate  1.493205         3.786179

## Randomized A/B outcome

Synthetic continuous scores by arm; Welch two-sample t-test and Cohen d (pooled SD).

```python
variant_a = ab_test.loc[ab_test["variant"] == "A", "score"]
variant_b = ab_test.loc[ab_test["variant"] == "B", "score"]
welch = stats.ttest_ind(variant_a, variant_b, equal_var=False)
n_a = variant_a.shape[0]
n_b = variant_b.shape[0]
pooled_sd = np.sqrt(((n_a - 1) * variant_a.var() + (n_b - 1) * variant_b.var()) / (n_a + n_b - 2))
cohen_d = (variant_b.mean() - variant_a.mean()) / pooled_sd
ab_summary = pd.DataFrame(
    {
        "n": [n_a, n_b],
        "mean": [variant_a.mean(), variant_b.mean()],
        "std": [variant_a.std(ddof=1), variant_b.std(ddof=1)],
        "sem": [variant_a.sem(), variant_b.sem()],
    },
    index=["A", "B"],
)
display(ab_summary)
print("\nWelch two-sample t-test:")
print(f"  t = {welch.statistic:.4f}")
print(f"  p-value = {welch.pvalue:.4g}")
print(f"Cohen's d (pooled SD): {cohen_d:.3f}")
```

    n        mean        std       sem
A  80   99.459862  11.391158  1.273570
B  75  107.157581  14.068873  1.624534


Welch two-sample t-test:
  t = -3.7291
  p-value = 0.0002766
Cohen's d (pooled SD): 0.603


## Customers: churn by plan and region

Contingency counts and chi-square test of independence between plan and churn label.

```python
plan_churn = pd.crosstab(customers["plan"], customers["churned"], margins=True)
plan_churn_pct = pd.crosstab(customers["plan"], customers["churned"], normalize="index") * 100
churn_by_plan = customers.groupby("plan", observed=False)["churned"].agg(["mean", "count"])
region_plan = pd.crosstab(customers["region"], customers["plan"], margins=True)
observed = pd.crosstab(customers["plan"], customers["churned"])
chi2_plan_churn = stats.chi2_contingency(observed)
print("Contingency table: Plan vs Churned")
display(plan_churn)
print("% Churned by Plan")
display(plan_churn_pct.round(2))
print("Churn rate by Plan")
display(churn_by_plan)
print("Contingency table: Region vs Plan")
display(region_plan)
print("Chi-square test of independence (plan vs churned):")
print(f"  chi2 = {chi2_plan_churn[0]:.4f}")
print(f"  p-value = {chi2_plan_churn[1]:.4g}")
print(f"  dof = {chi2_plan_churn[2]}")
```

Contingency table: Plan vs Churned


churned       0   1  All
plan                    
Basic        76  23   99
Enterprise   38   3   41
Pro          51   9   60
All         165  35  200

% Churned by Plan


churned         0      1
plan                    
Basic       76.77  23.23
Enterprise  92.68   7.32
Pro         85.00  15.00

Churn rate by Plan


                mean  count
plan                       
Basic       0.232323     99
Enterprise  0.073171     41
Pro         0.150000     60

Contingency table: Region vs Plan


plan    Basic  Enterprise  Pro  All
region                             
East       19          16    8   43
North      27          11   17   55
South      23           7   18   48
West       30           7   17   54
All        99          41   60  200

Chi-square test of independence (plan vs churned):
  chi2 = 5.4576
  p-value = 0.0653
  dof = 2


## Time structure (daily revenue)

Rolling mean and lag-1 autocorrelation as numeric substitutes for a line or ACF plot.

```python
window = 7
rolling = daily["revenue_usd"].rolling(window, min_periods=window).agg(["mean", "std"])
acf_lag1 = daily["revenue_usd"].autocorr(lag=1)
last_week = rolling.dropna().tail(5)
display(last_week)
print(f"Lag-1 autocorrelation: {acf_lag1:.3f}")

```

           mean         std
115  349.758571   95.852110
116  380.795714   81.009931
117  371.774286   72.534804
118  410.100000  146.642827
119  416.290000  143.463975

Lag-1 autocorrelation: -0.022
