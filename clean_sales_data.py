import pandas as pd

def clean_sales_data(path="input.txt"):
    """
    Extracts, cleans, and validates sales data.
    Args:
        path (str): path to the input file (.txt or .csv)
    Returns:
        pd.DataFrame: cleaned data
    """

    # === EXTRACT ===
    df = pd.read_csv(path)

    # === TRANSFORM ===
    # Drop duplicates
    df = df.drop_duplicates()

    # Drop rows with missing Product or Quantity Ordered
    df = df.dropna(subset=["Product", "Quantity Ordered"])

    # Strip whitespace from Product names
    df["Product"] = df["Product"].str.strip()

    # Convert numeric columns
    df["Quantity Ordered"] = pd.to_numeric(df["Quantity Ordered"], errors="coerce")
    df["Price Each"] = pd.to_numeric(df["Price Each"], errors="coerce")

    # Drop rows where conversion failed
    df = df.dropna(subset=["Quantity Ordered", "Price Each"])

    # Compute Total Price
    df["Total Price"] = df["Quantity Ordered"] * df["Price Each"]

    # === VALIDATE ===
    assert df["Total Price"].gt(0).all(), "Error: some total prices are not positive"
    assert df[["Product", "Quantity Ordered", "Price Each"]].notnull().all().all(), "Error: null values remain"

    return df


if __name__ == "__main__":
    cleaned_df = clean_sales_data("input.txt")
    print("✅ Cleaning completed successfully.\n")
    print(cleaned_df)
