import sys
import os

# Ensure the parent directory is in the path to import 'backend'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import time
from backend.llm_agent import run_llm, clear_user_memory, get_shopping_list

import re

TEST_CASES = [
    {
        "utterance": "Hi Priya, can you add 2 liters of milk and 500 grams of paneer to my list?",
        "expected_items": ["milk", "paneer"],
        "expected_quantities": ["2 liters", "500 g"],
        "expected_categories": ["liquid", "dairy"],
        "expected_confirmed": False
    },
    {
        "utterance": "Actually, I want 1 kg of paneer instead of 500 grams.",
        "expected_items": ["milk", "paneer"],
        "expected_quantities": ["2 liters", "1 kg"],
        "expected_categories": ["liquid", "dairy"],
        "expected_confirmed": False
    },
    {
        "utterance": "Please remove the milk, I don't need it.",
        "expected_items": ["paneer"],
        "expected_quantities": ["1 kg"],
        "expected_categories": ["dairy"],
        "expected_confirmed": False
    },
    {
        "utterance": "Add some apples.",
        "expected_items": ["paneer", "apple"],
        "expected_quantities": ["1 kg", "0.5 kg"],
        "expected_categories": ["dairy", "fruit"],
        "expected_confirmed": False
    },
    {
        "utterance": "Can you also add null grams of salt?",
        "expected_items": ["paneer", "apple", "salt"],
        "expected_quantities": ["1 kg", "0.5 kg", "250 g"],
        "expected_categories": ["dairy", "fruit", "spices"],
        "expected_confirmed": False
    },
    {
        "utterance": "Add 2 kilo rice please.",
        "expected_items": ["paneer", "apple", "salt", "rice"],
        "expected_quantities": ["1 kg", "0.5 kg", "250 g", "2 kg"],
        "expected_categories": ["dairy", "fruit", "spices", "grains"],
        "expected_confirmed": False
    },
    {
        "utterance": "Confirm my order.",
        "expected_items": ["paneer", "apple", "salt", "rice"],
        "expected_quantities": ["1 kg", "0.5 kg", "250 g", "2 kg"],
        "expected_categories": ["dairy", "fruit", "spices", "grains"],
        "expected_confirmed": True
    },
    {
        "utterance": "Actually wait, make it 3 kilos of rice and drop the salt.",
        "expected_items": ["paneer", "apple", "rice"],
        "expected_quantities": ["1 kg", "0.5 kg", "3 kg"],
        "expected_categories": ["dairy", "fruit", "grains"],
        "expected_confirmed": False
    },
    {
        "utterance": "What is the weather today?",
        "expected_items": ["paneer", "apple", "rice"],
        "expected_quantities": ["1 kg", "0.5 kg", "3 kg"],
        "expected_categories": ["dairy", "fruit", "grains"],
        "expected_confirmed": False
    },
    {
        "utterance": "Add to key low right please.",
        "expected_items": ["paneer", "apple", "rice"],
        "expected_quantities": ["1 kg", "0.5 kg", "2 kg"],
        "expected_categories": ["dairy", "fruit", "grains"],
        "expected_confirmed": False
    }
]

def exact_match(expected, actual):
    return re.search(r'\b' + re.escape(expected.lower()) + r'\b', actual.lower()) is not None

async def run_evaluation():
    test_user = "perf_eval_user"
    
    from backend.llm_agent import _get_state
    _get_state(test_user)["shopping_list"] = []
    
    print(f"{'='*60}")
    print("FRESHMART LLM AGENT PERFORMANCE EVALUATION")
    print(f"{'='*60}\n")
    
    total_latency = 0
    passed_tests = 0
    
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    
    qty_tp = 0
    qty_fp = 0
    qty_fn = 0
    
    cat_tp = 0
    cat_fp = 0
    cat_fn = 0

    metrics = {
        "item_accuracy": 0,
        "quantity_accuracy": 0,
        "category_accuracy": 0,
        "no_hallucinations": 0,
        "latency_under_3s": 0,
        "reply_length_under_200": 0,
        "confirmation_accuracy": 0
    }

    for i, test in enumerate(TEST_CASES):
        print(f"Test {i+1}/{len(TEST_CASES)}: '{test['utterance']}'")
        
        start_time = time.time()
        reply, is_confirmed = await run_llm(test_user, test["utterance"])
        latency = time.time() - start_time
        
        total_latency += latency
        
        current_list = get_shopping_list(test_user)
        current_item_names = [item.get('name', '').lower() for item in current_list]
        current_quantities = [item.get('quantity', '').lower() for item in current_list]
        current_categories = [item.get('category', '').lower() for item in current_list]
        
        # Calculate precision / recall for items
        for expected in test["expected_items"]:
            if any(exact_match(expected, name) for name in current_item_names):
                true_positives += 1
            else:
                false_negatives += 1
                
        for actual in current_item_names:
            if not any(exact_match(exp, actual) for exp in test["expected_items"]):
                false_positives += 1
                
        # Calculate precision / recall for quantities
        for expected in test["expected_quantities"]:
            if any(exact_match(expected, qty) for qty in current_quantities):
                qty_tp += 1
            else:
                qty_fn += 1
                
        for actual in current_quantities:
            if not any(exact_match(exp, actual) for exp in test["expected_quantities"]):
                qty_fp += 1
                
        # Calculate precision / recall for categories
        for expected in test["expected_categories"]:
            if any(exact_match(expected, cat) for cat in current_categories):
                cat_tp += 1
            else:
                cat_fn += 1
                
        for actual in current_categories:
            if not any(exact_match(exp, actual) for exp in test["expected_categories"]):
                cat_fp += 1
        
        # Check Items
        items_match = all(any(exact_match(exp, name) for name in current_item_names) for exp in test["expected_items"])
        if items_match: metrics["item_accuracy"] += 1
            
        # Check Quantities
        quantities_match = all(any(exact_match(exp, qty) for qty in current_quantities) for exp in test["expected_quantities"])
        if quantities_match: metrics["quantity_accuracy"] += 1
            
        # Check Categories
        categories_match = all(any(exact_match(exp, cat) for cat in current_categories) for exp in test["expected_categories"])
        if categories_match: metrics["category_accuracy"] += 1
            
        # Check Hallucinations (No extra items)
        no_hallucinations = len(current_list) == len(test["expected_items"])
        if no_hallucinations: metrics["no_hallucinations"] += 1
            
        # Check Latency (< 3.0s threshold)
        latency_ok = latency <= 3.0
        if latency_ok: metrics["latency_under_3s"] += 1
            
        # Check Reply length
        reply_ok = len(reply) <= 200
        if reply_ok: metrics["reply_length_under_200"] += 1
            
        # Check Confirmation
        conf_match = (is_confirmed == test["expected_confirmed"])
        if conf_match: metrics["confirmation_accuracy"] += 1
            
        passed = (items_match and quantities_match and categories_match and 
                  no_hallucinations and latency_ok and reply_ok and conf_match)
                  
        if passed:
            passed_tests += 1
            status = "PASS"
        else:
            status = "FAIL"
            
        print(f"  Latency:   {latency:.2f} seconds")
        print(f"  Reply:     {reply}")
        print(f"  Cart:      {current_list}")
        print(f"  Confirmed: {is_confirmed}")
        print(f"  Status:    {status}")
        
        # Print failed reasons
        if not passed:
            reasons = []
            if not items_match: reasons.append("Item Mismatch")
            if not quantities_match: reasons.append("Quantity Mismatch")
            if not categories_match: reasons.append("Category Mismatch")
            if not no_hallucinations: reasons.append("Hallucinated Items Detected")
            if not latency_ok: reasons.append("High Latency (> 3s)")
            if not reply_ok: reasons.append("Reply Too Long (> 200 chars)")
            if not conf_match: reasons.append("Confirmation Status Mismatch")
            print(f"  Failures:  {', '.join(reasons)}")
        print()

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    qty_precision = qty_tp / (qty_tp + qty_fp) if (qty_tp + qty_fp) > 0 else 0
    qty_recall = qty_tp / (qty_tp + qty_fn) if (qty_tp + qty_fn) > 0 else 0
    qty_f1 = 2 * (qty_precision * qty_recall) / (qty_precision + qty_recall) if (qty_precision + qty_recall) > 0 else 0
    
    cat_precision = cat_tp / (cat_tp + cat_fp) if (cat_tp + cat_fp) > 0 else 0
    cat_recall = cat_tp / (cat_tp + cat_fn) if (cat_tp + cat_fn) > 0 else 0
    cat_f1 = 2 * (cat_precision * cat_recall) / (cat_precision + cat_recall) if (cat_precision + cat_recall) > 0 else 0

    print(f"{'='*60}")
    print("EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total Tests: {len(TEST_CASES)}")
    print(f"Passed:      {passed_tests}")
    print(f"Failed:      {len(TEST_CASES) - passed_tests}")
    if len(TEST_CASES) > 0:
        print(f"Avg Latency: {total_latency / len(TEST_CASES):.2f} seconds")
        
    print("\nMETRICS BREAKDOWN:")
    for metric, count in metrics.items():
        percentage = (count / len(TEST_CASES)) * 100
        print(f"  {metric.replace('_', ' ').title():<25}: {count}/{len(TEST_CASES)} ({percentage:.0f}%)")
        
    print("\nPRECISION, RECALL AND F1-SCORE:")
    print("  ITEMS:")
    print(f"    Precision:               {precision:.2%}")
    print(f"    Recall:                  {recall:.2%}")
    print(f"    F1-Score:                {f1:.2%}")
    print("  QUANTITIES:")
    print(f"    Precision:               {qty_precision:.2%}")
    print(f"    Recall:                  {qty_recall:.2%}")
    print(f"    F1-Score:                {qty_f1:.2%}")
    print("  CATEGORIES:")
    print(f"    Precision:               {cat_precision:.2%}")
    print(f"    Recall:                  {cat_recall:.2%}")
    print(f"    F1-Score:                {cat_f1:.2%}")
    print(f"{'='*60}\n")
    
    # Cleanup
    clear_user_memory(test_user)

if __name__ == "__main__":
    asyncio.run(run_evaluation())
