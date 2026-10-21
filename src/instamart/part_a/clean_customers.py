"""Task 3: clean customers (city, gender, age, signup_date) in the order the brief states."""
import logging

import pandas as pd

from instamart import config

log = logging.getLogger(__name__)


def standardise_city(city: pd.Series) -> pd.Series:
    """Strip surrounding spaces and apply title case ('  mumbai ' -> 'Mumbai')."""
    return city.str.strip().str.title()


def map_gender(gender: pd.Series) -> pd.Series:
    """Map every raw gender spelling to male/female; blanks and anything unrecognised become unknown."""
    return gender.str.strip().str.lower().map(config.GENDER_MAP).fillna(config.GENDER_UNKNOWN)


def invalidate_impossible_ages(age: pd.Series) -> pd.Series:
    """Return age with values outside AGE_MIN..AGE_MAX replaced by missing."""
    return age.where(age.between(config.AGE_MIN, config.AGE_MAX))


def fill_age_by_city_median(df: pd.DataFrame) -> pd.Series:
    """Fill missing ages with the median age of the customer's (standardised) city via groupby + transform."""
    city_median = df.groupby("city")["age"].transform("median")
    return df["age"].fillna(city_median)


def clean_customers(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Apply rules (a)-(d) and return the clean table and a list of {rule, changed} records."""
    df = raw.copy()
    rules: list[dict] = []

    city = standardise_city(df["city"])
    rules.append({"rule": "city: strip spaces + title case", "changed": int((city != df["city"]).sum())})
    df["city"] = city

    gender = map_gender(df["gender"])
    rules.append({"rule": "gender: blank -> unknown", "changed": int(df["gender"].isna().sum())})
    rules.append({"rule": "gender: spelling mapped to male/female",
                  "changed": int((df["gender"].notna() & (gender != df["gender"])).sum())})
    df["gender"] = gender

    age = invalidate_impossible_ages(df["age"])
    rules.append({"rule": "age: outside 10-100 set to missing",
                  "changed": int((df["age"].notna() & age.isna()).sum())})
    df["age"] = age
    missing_before = int(df["age"].isna().sum())
    df["age"] = fill_age_by_city_median(df)
    rules.append({"rule": "age: missing filled with city median (groupby + transform)",
                  "changed": missing_before - int(df["age"].isna().sum())})

    df["signup_date"] = pd.to_datetime(df["signup_date"], format=config.DATE_FORMAT)
    rules.append({"rule": "signup_date: text converted to datetime", "changed": int(df["signup_date"].notna().sum())})

    log.info("customers cleaned: %d rows", len(df))
    return df, rules


def customer_summary(customers: pd.DataFrame) -> dict:
    """Return the post-cleaning reference figures for the customers table."""
    return {
        "rows": int(len(customers)),
        "city_counts": {k: int(v) for k, v in customers["city"].value_counts().items()},
        "gender_counts": {k: int(v) for k, v in customers["gender"].value_counts().items()},
        "missing_age": int(customers["age"].isna().sum()),
        "age_min": float(customers["age"].min()),
        "age_max": float(customers["age"].max()),
    }
