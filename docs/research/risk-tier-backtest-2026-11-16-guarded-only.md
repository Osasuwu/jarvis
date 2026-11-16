# Risk-tier backtest: jarvis PRs merged 2026-09-01 – 2026-11-15

- Command: `python scripts/risk_tier_backtest.py --since 2026-09-01 --until 2026-11-15 --out docs/research/risk-tier-backtest-2026-11-16-guarded-only.md`
- Window: merged 2026-09-01 to 2026-11-15 (UTC dates, inclusive). Run 2026-11-16.
- PRs: **196**, one row each below.
- Rules: `config/protected-paths.json` and `config/plan_review.yaml` at the commit of this report, not at each PR's base. Inputs and their sources: `scripts/risk_tier_backtest.py` docstring. Issue: #2199; thresholds lock in #2200.

## Prediction

Pre-registered (decision PR #2197): HIGH share at or below 25%. Measured: **27%** (52 of 196). The prediction **missed**.

## Distribution by threshold variant

Churn and areas only move PRs between LOW and MEDIUM, so HIGH is the same in every variant.

| churn > | areas >= | HIGH | MEDIUM | LOW |
|---|---|---|---|---|
| 300 | 2 | 27% | 25% | 48% |
| 300 | 3 | 27% | 14% | 60% |
| 400 (baseline) | 2 | 27% | 24% | 49% |
| 400 | 3 | 27% | 12% | 61% |
| 600 | 2 | 27% | 24% | 49% |
| 600 | 3 | 27% | 11% | 63% |

## Inputs that fired (baseline)

| input | PRs |
|---|---|
| path:machinery | 118 |
| areas>=2 | 81 |
| test weakening | 49 |
| churn>400 | 47 |
| docs-only | 36 |
| path:gate | 35 |
| path:hitl | 19 |
| path:guarded | 6 |

Touched a `hitl`, `machinery` or `gate` path but no `guarded` one: 115 PRs, 33 of them HIGH by another input. Only the `guarded` bucket floors the tier (#2200).

Test-weakening reasons (one PR can carry several):

| reason | occurrences |
|---|---|
| test function removed | 254 |
| test file removed | 209 |
| skip/xfail added | 13 |

Comment-only exemption: 6 PRs touched a guarded path, 0 of them changed only `.py` files, 0 were exempted, 0 could not be computed.

## Weekly shares

Baseline (churn > 400, areas >= 2) HIGH / MEDIUM / LOW, then the MEDIUM share under each other variant (`c` churn threshold, `a` areas minimum). Week = Monday, UTC.

| week | PRs | HIGH | MEDIUM | LOW | MED c300 a2 | MED c300 a3 | MED c400 a3 | MED c600 a2 | MED c600 a3 |
|---|---|---|---|---|---|---|---|---|---|
| 2026-08-31 | 19 | 26% | 11% | 63% | 16% | 16% | 11% | 11% | 11% |
| 2026-09-07 | 32 | 41% | 16% | 44% | 16% | 9% | 9% | 16% | 9% |
| 2026-09-14 | 17 | 6% | 12% | 82% | 12% | 0% | 0% | 12% | 0% |
| 2026-09-21 | 12 | 33% | 42% | 25% | 42% | 0% | 0% | 42% | 0% |
| 2026-09-28 | 9 | 22% | 11% | 67% | 11% | 11% | 11% | 11% | 11% |
| 2026-10-05 | 33 | 21% | 27% | 52% | 27% | 18% | 12% | 27% | 12% |
| 2026-10-12 | 41 | 37% | 22% | 41% | 22% | 7% | 7% | 22% | 7% |
| 2026-10-19 | 14 | 14% | 43% | 43% | 43% | 36% | 36% | 43% | 29% |
| 2026-10-26 | 5 | 20% | 40% | 40% | 40% | 0% | 0% | 40% | 0% |
| 2026-11-02 | 8 | 25% | 38% | 38% | 38% | 38% | 38% | 38% | 38% |
| 2026-11-09 | 6 | 0% | 67% | 33% | 67% | 50% | 50% | 50% | 17% |

## Unreadable file lists

None: every PR's file list was read in full.

## Per PR

Churn excludes lockfiles; areas are top-level path components, `tests/` excluded.

| PR | merged | tier | churn | areas | inputs fired |
|---|---|---|---|---|---|
| #1758 | 2026-09-01 | HIGH | 1031 | 5 | path:guarded; churn>400; areas>=2 |
| #1760 | 2026-09-01 | MEDIUM | 2205 | 6 | path:machinery; churn>400; areas>=2 |
| #1766 | 2026-09-01 | LOW | 18 | 1 | none |
| #1768 | 2026-09-02 | LOW | 51 | 1 | path:machinery; path:gate |
| #1770 | 2026-09-02 | LOW | 0 | 0 | none |
| #1773 | 2026-09-02 | LOW | 182 | 1 | none |
| #1771 | 2026-09-02 | LOW | 336 | 1 | none |
| #1772 | 2026-09-02 | LOW | 164 | 2 | path:machinery; docs-only |
| #1776 | 2026-09-02 | LOW | 246 | 1 | none |
| #1778 | 2026-09-02 | LOW | 63 | 1 | none |
| #1779 | 2026-09-02 | LOW | 4 | 1 | docs-only |
| #1781 | 2026-09-02 | LOW | 66 | 1 | none |
| #1783 | 2026-09-02 | HIGH | 11657 | 7 | path:guarded; path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #1784 | 2026-09-02 | HIGH | 1910 | 3 | test weakening; churn>400; areas>=2 |
| #1785 | 2026-09-02 | LOW | 100 | 1 | none |
| #1786 | 2026-09-02 | HIGH | 335 | 2 | test weakening; areas>=2 |
| #1811 | 2026-09-06 | MEDIUM | 843 | 1 | path:hitl; path:machinery; churn>400 |
| #1812 | 2026-09-06 | HIGH | 893 | 8 | path:hitl; path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #1813 | 2026-09-06 | LOW | 212 | 1 | none |
| #1814 | 2026-09-07 | HIGH | 678 | 2 | test weakening; churn>400; areas>=2 |
| #1819 | 2026-09-07 | LOW | 126 | 1 | path:machinery |
| #1817 | 2026-09-07 | LOW | 110 | 2 | docs-only |
| #1821 | 2026-09-07 | HIGH | 5126 | 12 | path:hitl; path:machinery; test weakening; churn>400; areas>=2 |
| #1823 | 2026-09-07 | LOW | 2 | 1 | docs-only |
| #1828 | 2026-09-07 | MEDIUM | 1141 | 7 | path:machinery; churn>400; areas>=2 |
| #1830 | 2026-09-07 | LOW | 79 | 0 | none |
| #1829 | 2026-09-07 | MEDIUM | 26 | 2 | path:machinery; areas>=2 |
| #1831 | 2026-09-07 | HIGH | 166 | 1 | test weakening |
| #1832 | 2026-09-07 | HIGH | 299 | 1 | test weakening |
| #1833 | 2026-09-07 | HIGH | 2348 | 9 | path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #1835 | 2026-09-07 | HIGH | 5515 | 1 | path:machinery; path:gate; test weakening; churn>400 |
| #1837 | 2026-09-07 | HIGH | 1432 | 2 | test weakening; churn>400; areas>=2 |
| #1840 | 2026-09-07 | LOW | 13 | 0 | none |
| #1839 | 2026-09-07 | LOW | 130 | 1 | path:machinery |
| #1842 | 2026-09-08 | LOW | 20 | 1 | path:machinery; path:gate |
| #1843 | 2026-09-08 | LOW | 196 | 1 | path:machinery |
| #1845 | 2026-09-08 | LOW | 2 | 1 | docs-only |
| #1849 | 2026-09-08 | LOW | 112 | 1 | path:machinery |
| #1852 | 2026-09-08 | HIGH | 204 | 1 | path:machinery; path:gate; test weakening |
| #1853 | 2026-09-08 | LOW | 12 | 1 | docs-only |
| #1851 | 2026-09-08 | HIGH | 19561 | 11 | path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #1855 | 2026-09-08 | LOW | 9 | 1 | docs-only |
| #1864 | 2026-09-08 | LOW | 17 | 1 | none |
| #1867 | 2026-09-08 | HIGH | 46685 | 18 | path:guarded; path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #1868 | 2026-09-09 | HIGH | 45103 | 15 | path:hitl; path:machinery; test weakening; churn>400; areas>=2 |
| #1870 | 2026-09-09 | HIGH | 888 | 1 | test weakening; churn>400 |
| #1871 | 2026-09-09 | LOW | 37 | 1 | docs-only |
| #1869 | 2026-09-09 | MEDIUM | 124 | 2 | path:machinery; areas>=2 |
| #1873 | 2026-09-09 | HIGH | 48520 | 9 | path:hitl; path:guarded; path:machinery; test weakening; churn>400; areas>=2 |
| #1878 | 2026-09-12 | MEDIUM | 11 | 3 | path:machinery; areas>=2 |
| #1879 | 2026-09-12 | MEDIUM | 48 | 4 | path:hitl; path:machinery; areas>=2 |
| #1883 | 2026-09-15 | LOW | 203 | 1 | none |
| #1884 | 2026-09-15 | LOW | 705 | 2 | docs-only |
| #1886 | 2026-09-15 | LOW | 157 | 1 | path:machinery |
| #1889 | 2026-09-16 | LOW | 92 | 1 | docs-only |
| #1888 | 2026-09-16 | LOW | 54 | 2 | docs-only |
| #1899 | 2026-09-16 | LOW | 51 | 1 | path:machinery; path:gate |
| #1900 | 2026-09-16 | LOW | 287 | 1 | path:machinery; path:gate |
| #1887 | 2026-09-17 | HIGH | 603 | 1 | path:machinery; test weakening; churn>400 |
| #1896 | 2026-09-17 | LOW | 127 | 1 | docs-only |
| #1903 | 2026-09-17 | LOW | 141 | 1 | path:machinery |
| #1905 | 2026-09-17 | LOW | 79 | 1 | path:machinery; path:gate |
| #1906 | 2026-09-17 | LOW | 78 | 1 | path:machinery |
| #1907 | 2026-09-17 | LOW | 30 | 1 | path:machinery |
| #1908 | 2026-09-17 | LOW | 20 | 0 | none |
| #1909 | 2026-09-17 | MEDIUM | 20 | 2 | path:machinery; areas>=2 |
| #1910 | 2026-09-17 | LOW | 7 | 1 | path:machinery |
| #1912 | 2026-09-17 | MEDIUM | 2 | 2 | path:machinery; areas>=2 |
| #1915 | 2026-09-22 | LOW | 1288 | 1 | docs-only |
| #1917 | 2026-09-24 | MEDIUM | 53 | 2 | areas>=2 |
| #1919 | 2026-09-24 | MEDIUM | 41 | 2 | path:hitl; path:machinery; areas>=2 |
| #1920 | 2026-09-24 | HIGH | 44 | 4 | test weakening; areas>=2 |
| #1921 | 2026-09-24 | MEDIUM | 228 | 2 | path:machinery; areas>=2 |
| #1922 | 2026-09-24 | MEDIUM | 39 | 2 | areas>=2 |
| #1916 | 2026-09-24 | LOW | 187 | 1 | docs-only |
| #1924 | 2026-09-24 | HIGH | 128 | 5 | path:hitl; path:machinery; test weakening; areas>=2 |
| #1928 | 2026-09-24 | HIGH | 83 | 1 | path:machinery; test weakening |
| #1931 | 2026-09-24 | MEDIUM | 27 | 2 | path:machinery; areas>=2 |
| #1930 | 2026-09-24 | HIGH | 5722 | 8 | path:hitl; path:machinery; test weakening; churn>400; areas>=2 |
| #1933 | 2026-09-24 | LOW | 10 | 1 | path:machinery; path:gate |
| #1937 | 2026-09-30 | LOW | 248 | 1 | path:machinery |
| #1946 | 2026-09-30 | HIGH | 550 | 0 | test weakening; churn>400 |
| #1950 | 2026-09-30 | MEDIUM | 214 | 3 | path:hitl; path:machinery; areas>=2 |
| #1952 | 2026-09-30 | LOW | 1866 | 1 | docs-only |
| #1947 | 2026-09-30 | LOW | 94 | 1 | path:machinery; path:gate |
| #1954 | 2026-10-01 | LOW | 5 | 1 | path:machinery |
| #1956 | 2026-10-01 | HIGH | 146 | 8 | path:machinery; path:gate; test weakening; areas>=2 |
| #1962 | 2026-10-01 | LOW | 2216 | 1 | docs-only |
| #1963 | 2026-10-01 | LOW | 3 | 1 | none |
| #1972 | 2026-10-06 | HIGH | 248 | 2 | test weakening; areas>=2 |
| #1973 | 2026-10-06 | LOW | 40 | 1 | none |
| #1974 | 2026-10-06 | LOW | 516 | 1 | docs-only |
| #1975 | 2026-10-06 | LOW | 1468 | 1 | docs-only |
| #1977 | 2026-10-06 | LOW | 19 | 1 | path:machinery |
| #1980 | 2026-10-06 | LOW | 414 | 2 | docs-only |
| #1986 | 2026-10-07 | LOW | 34 | 1 | path:machinery |
| #1989 | 2026-10-07 | MEDIUM | 343 | 2 | path:machinery; areas>=2 |
| #1988 | 2026-10-07 | LOW | 125 | 1 | none |
| #1987 | 2026-10-07 | MEDIUM | 79 | 2 | path:machinery; areas>=2 |
| #1990 | 2026-10-07 | LOW | 6 | 1 | path:machinery; path:gate |
| #1982 | 2026-10-07 | HIGH | 6882 | 2 | path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #1997 | 2026-10-07 | LOW | 4 | 1 | docs-only |
| #2001 | 2026-10-07 | LOW | 11 | 1 | docs-only |
| #2003 | 2026-10-07 | LOW | 1213 | 2 | docs-only |
| #2016 | 2026-10-07 | HIGH | 443 | 2 | path:machinery; test weakening; churn>400; areas>=2 |
| #2019 | 2026-10-07 | MEDIUM | 707 | 1 | path:machinery; churn>400 |
| #2021 | 2026-10-07 | HIGH | 1314 | 6 | path:machinery; test weakening; churn>400; areas>=2 |
| #2022 | 2026-10-07 | LOW | 248 | 1 | path:machinery |
| #2023 | 2026-10-08 | MEDIUM | 765 | 2 | path:machinery; path:gate; churn>400; areas>=2 |
| #2026 | 2026-10-08 | MEDIUM | 328 | 2 | path:machinery; areas>=2 |
| #2028 | 2026-10-08 | MEDIUM | 919 | 1 | path:machinery; churn>400 |
| #2029 | 2026-10-08 | MEDIUM | 1374 | 1 | path:machinery; churn>400 |
| #2030 | 2026-10-08 | HIGH | 1060 | 5 | path:hitl; path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #2031 | 2026-10-08 | LOW | 97 | 1 | path:machinery |
| #2032 | 2026-10-08 | MEDIUM | 201 | 2 | path:machinery; areas>=2 |
| #2035 | 2026-10-08 | LOW | 63 | 1 | docs-only |
| #2033 | 2026-10-08 | HIGH | 952 | 2 | path:machinery; test weakening; churn>400; areas>=2 |
| #2034 | 2026-10-08 | HIGH | 2870 | 4 | path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #2037 | 2026-10-10 | LOW | 53 | 1 | none |
| #2041 | 2026-10-11 | LOW | 12 | 1 | path:machinery |
| #2040 | 2026-10-11 | LOW | 88 | 2 | docs-only |
| #2042 | 2026-10-11 | MEDIUM | 3 | 2 | path:hitl; path:machinery; areas>=2 |
| #2046 | 2026-10-14 | HIGH | 361 | 2 | path:machinery; path:gate; test weakening; areas>=2 |
| #2050 | 2026-10-14 | HIGH | 1580 | 4 | path:hitl; path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #2049 | 2026-10-15 | LOW | 159 | 1 | path:machinery |
| #2047 | 2026-10-15 | LOW | 36 | 1 | path:machinery |
| #2052 | 2026-10-15 | HIGH | 474 | 2 | path:machinery; test weakening; churn>400; areas>=2 |
| #2053 | 2026-10-15 | LOW | 196 | 1 | none |
| #2056 | 2026-10-15 | MEDIUM | 95 | 2 | path:machinery; areas>=2 |
| #2064 | 2026-10-16 | MEDIUM | 176 | 3 | path:machinery; areas>=2 |
| #2063 | 2026-10-16 | HIGH | 737 | 2 | path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #2061 | 2026-10-16 | LOW | 128 | 1 | path:machinery |
| #2060 | 2026-10-16 | LOW | 104 | 1 | path:machinery |
| #1992 | 2026-10-16 | MEDIUM | 4 | 2 | path:machinery; areas>=2 |
| #2002 | 2026-10-16 | LOW | 2 | 1 | path:machinery |
| #2054 | 2026-10-16 | LOW | 14 | 1 | path:machinery; path:gate |
| #2066 | 2026-10-16 | MEDIUM | 214 | 2 | path:machinery; areas>=2 |
| #2075 | 2026-10-16 | MEDIUM | 1068 | 5 | path:machinery; path:gate; churn>400; areas>=2 |
| #2077 | 2026-10-16 | LOW | 10 | 1 | path:machinery |
| #2078 | 2026-10-16 | MEDIUM | 251 | 2 | path:machinery; path:gate; areas>=2 |
| #2080 | 2026-10-16 | HIGH | 1597 | 3 | path:machinery; path:gate; test weakening; churn>400; areas>=2 |
| #2083 | 2026-10-16 | HIGH | 329 | 2 | path:machinery; path:gate; test weakening; areas>=2 |
| #2084 | 2026-10-16 | MEDIUM | 163 | 2 | path:machinery; path:gate; areas>=2 |
| #2086 | 2026-10-16 | HIGH | 128 | 1 | path:machinery; test weakening |
| #2090 | 2026-10-16 | LOW | 92 | 1 | docs-only |
| #2091 | 2026-10-16 | MEDIUM | 182 | 4 | path:hitl; path:machinery; areas>=2 |
| #2092 | 2026-10-16 | LOW | 8 | 1 | path:machinery |
| #2093 | 2026-10-16 | HIGH | 1267 | 1 | path:machinery; path:gate; test weakening; churn>400 |
| #2094 | 2026-10-17 | HIGH | 2034 | 1 | path:machinery; test weakening; churn>400 |
| #2095 | 2026-10-17 | LOW | 8 | 1 | path:machinery |
| #2096 | 2026-10-17 | HIGH | 472 | 2 | path:machinery; test weakening; churn>400; areas>=2 |
| #2098 | 2026-10-17 | HIGH | 496 | 2 | path:machinery; test weakening; churn>400; areas>=2 |
| #2100 | 2026-10-17 | LOW | 8 | 1 | path:machinery |
| #2101 | 2026-10-17 | LOW | 111 | 2 | docs-only |
| #2102 | 2026-10-17 | MEDIUM | 179 | 2 | path:machinery; path:gate; areas>=2 |
| #2106 | 2026-10-17 | LOW | 798 | 1 | docs-only |
| #2108 | 2026-10-17 | LOW | 88 | 1 | docs-only |
| #2109 | 2026-10-17 | HIGH | 254 | 3 | path:hitl; path:machinery; test weakening; areas>=2 |
| #2113 | 2026-10-17 | LOW | 54 | 1 | none |
| #2114 | 2026-10-17 | HIGH | 619 | 1 | test weakening; churn>400 |
| #2112 | 2026-10-17 | HIGH | 55 | 1 | test weakening |
| #2117 | 2026-10-17 | LOW | 116 | 1 | docs-only |
| #2118 | 2026-10-17 | HIGH | 118 | 0 | test weakening |
| #2120 | 2026-10-19 | LOW | 37 | 2 | path:machinery; docs-only |
| #2121 | 2026-10-20 | HIGH | 1243 | 2 | path:machinery; test weakening; churn>400; areas>=2 |
| #2139 | 2026-10-20 | MEDIUM | 223 | 4 | path:hitl; path:machinery; areas>=2 |
| #2137 | 2026-10-20 | MEDIUM | 57 | 2 | path:machinery; areas>=2 |
| #2138 | 2026-10-20 | MEDIUM | 587 | 2 | path:machinery; churn>400; areas>=2 |
| #2141 | 2026-10-20 | LOW | 6 | 1 | docs-only |
| #2151 | 2026-10-20 | LOW | 18 | 1 | none |
| #2150 | 2026-10-20 | MEDIUM | 1472 | 2 | churn>400; areas>=2 |
| #2154 | 2026-10-20 | LOW | 57 | 1 | none |
| #2156 | 2026-10-21 | LOW | 28 | 1 | path:machinery; docs-only |
| #2158 | 2026-10-21 | MEDIUM | 405 | 3 | path:machinery; churn>400; areas>=2 |
| #2159 | 2026-10-21 | MEDIUM | 44 | 3 | path:hitl; path:machinery; areas>=2 |
| #2164 | 2026-10-22 | HIGH | 22 | 3 | path:guarded; areas>=2 |
| #2165 | 2026-10-24 | LOW | 29 | 1 | none |
| #2166 | 2026-10-27 | MEDIUM | 11 | 2 | path:machinery; path:gate; areas>=2 |
| #2169 | 2026-10-28 | HIGH | 43 | 3 | path:hitl; path:machinery; test weakening; areas>=2 |
| #2173 | 2026-10-28 | LOW | 167 | 1 | none |
| #2176 | 2026-10-29 | LOW | 418 | 1 | docs-only |
| #2180 | 2026-10-29 | MEDIUM | 78 | 2 | path:machinery; path:gate; areas>=2 |
| #2185 | 2026-11-04 | HIGH | 277 | 2 | path:guarded; areas>=2 |
| #2186 | 2026-11-04 | LOW | 8 | 1 | path:machinery; docs-only |
| #2187 | 2026-11-04 | MEDIUM | 36 | 6 | path:machinery; areas>=2 |
| #2189 | 2026-11-04 | MEDIUM | 119 | 3 | path:machinery; path:gate; areas>=2 |
| #2192 | 2026-11-04 | LOW | 28 | 2 | docs-only |
| #2193 | 2026-11-04 | HIGH | 137 | 3 | path:machinery; test weakening; areas>=2 |
| #2194 | 2026-11-04 | LOW | 16 | 1 | path:machinery; path:gate |
| #2196 | 2026-11-04 | MEDIUM | 32 | 3 | path:hitl; path:machinery; areas>=2 |
| #2197 | 2026-11-15 | LOW | 119 | 1 | docs-only |
| #2206 | 2026-11-15 | MEDIUM | 1009 | 2 | churn>400; areas>=2 |
| #2207 | 2026-11-15 | MEDIUM | 8 | 2 | path:machinery; areas>=2 |
| #2212 | 2026-11-15 | LOW | 33 | 1 | none |
| #2213 | 2026-11-15 | MEDIUM | 518 | 1 | churn>400 |
| #2209 | 2026-11-15 | MEDIUM | 448 | 2 | path:machinery; churn>400; areas>=2 |
