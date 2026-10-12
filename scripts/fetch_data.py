from sklift.datasets import fetch_hillstrom
import pandas as pd

d1 = fetch_hillstrom(target_col='visit')
d2 = fetch_hillstrom(target_col='conversion')
d3 = fetch_hillstrom(target_col='spend')

df = d1['data'].copy()
t = d1['treatment']

df['segment'] = t.values
df['treatment'] = (t != 'No E-Mail').astype(int)
df['visit'] = d1['target'].values
df['conversion'] = d2['target'].values
df['spend'] = d3['target'].values

print('Shape:', df.shape)
print('Treatment counts:', df['treatment'].value_counts().to_dict())
print('Segment counts:', df['segment'].value_counts().to_dict())

df.to_csv('data/raw/hillstrom.csv', index=False)
print('Saved to data/raw/hillstrom.csv')