import pytest
from ai.evaluate import run_comparative_evaluation

def test_comparative_evaluation_execution():
    # Run a fast 40-step comparative evaluation
    results = run_comparative_evaluation(steps=40, seed=123)
    
    assert "baseline" in results
    assert "ai_controller" in results
    assert "improvement" in results
    
    # Assert key metrics exist
    assert "total_reward" in results["baseline"]
    assert "total_reward" in results["ai_controller"]
    assert "diesel_fuel_saved_liters" in results["improvement"]
    assert "carbon_offset_kg_co2" in results["improvement"]
    
    # Critical availability must be calculated
    assert results["ai_controller"]["critical_availability_pct"] >= 0.0
    assert results["baseline"]["critical_availability_pct"] >= 0.0
