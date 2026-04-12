#!/usr/bin/env python3
"""
FAOSTAT Crop and Vegetable Analysis
File: crop_analysis.py (NOT faostat.py!)
"""

import faostat
import pandas as pd

def main():
    print("FAOSTAT Crop and Vegetable Analysis")
    print("=" * 40)
    
    # 1. List available datasets (correct method)
    print("\n1. Available Datasets:")
    try:
        datasets = faostat.list_datasets()
        print(f"Found {len(datasets)} datasets")
        
        # Show first 10 datasets
        for i, dataset in enumerate(datasets[:10]):
            print(f"{i+1}. {dataset[0]}: {dataset[1]}")
    except Exception as e:
        print(f"Error listing datasets: {e}")
    
    # 2. Get parameters for QCL dataset
    print("\n2. Exploring QCL Dataset Parameters:")
    try:
        qcl_params = faostat.list_pars('QCL')
        print("QCL parameters available:")
        for param in qcl_params:
            print(f"  - {param}")
    except Exception as e:
        print(f"Error getting QCL parameters: {e}")
    
    # 3. Get specific parameter values
    print("\n3. Getting Item Codes for Vegetables:")
    try:
        items = faostat.get_par('QCL', 'item')
        # Filter for common vegetables
        vegetable_items = [item for item in items if any(veg in item[1].lower() 
                          for veg in ['tomato', 'potato', 'onion', 'carrot'])]
        
        print("Found vegetable items:")
        for item in vegetable_items[:5]:
            print(f"  Code: {item[0]}, Name: {item[1]}")
    except Exception as e:
        print(f"Error getting items: {e}")
    
    # 4. Fetch actual crop production data
    print("\n4. Fetching Crop Production Data:")
    crop_params = {
        'element': [5312, 5510],  # Area harvested, Production
        'item': ['388', '116', '403'],  # Tomatoes, Potatoes, Onions
        'area': ['231'],  # United States
        'year': [2020, 2021, 2022]
    }
    
    try:
        production_data = faostat.get_data_df('QCL', pars=crop_params)
        print(f"Production data shape: {production_data.shape}")
        
        if not production_data.empty:
            print("\nFirst few rows:")
            print(production_data.head())
            
            # Basic analysis
            print("\n5. Basic Analysis:")
            analysis = production_data.groupby(['Area', 'Item', 'Element'])['Value'].agg(['mean', 'sum']).round(2)
            print(analysis)
            
            # Export results
            production_data.to_csv('faostat_crop_data.csv', index=False)
            print("\n6. Data exported to 'faostat_crop_data.csv'")
        else:
            print("No data returned. Check your parameters.")
            
    except Exception as e:
        print(f"Error fetching production data: {e}")

if __name__ == "__main__":
    main()
