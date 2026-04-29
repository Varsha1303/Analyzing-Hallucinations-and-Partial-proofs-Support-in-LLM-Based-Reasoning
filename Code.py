import json
import re
import time
from google import genai
from z3 import Solver, Bool, And, Or, Not, Implies, ForAll, sat, unsat

# ==========================================
# 1. API CONFIGURATION — key rotation pool
# ==========================================
_API_KEYS = [
# add API Keys I have used 3-4 different API keys
]
_key_index = 0

def _get_client():
    return genai.Client(api_key=_API_KEYS[_key_index])

MODEL_ID = "gemini-2.5-flash"

def _call_api(prompt, max_retries=5):
    global _key_index
    rate_attempts = 0  # counts only transient backoff retries

    while True:
        try:
            client = _get_client()
            response = client.models.generate_content(model=MODEL_ID, contents=prompt)
            return response.text

        except Exception as e:
            error_msg = str(e)

            # Daily quota exhausted — rotate to next key immediately
            if "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
                next_index = _key_index + 1
                if next_index >= len(_API_KEYS):
                    raise RuntimeError("All API keys have exhausted their daily quota.") from e
                print(f"Key {_key_index + 1} quota exhausted. Switching to key {next_index + 1}...")
                _key_index = next_index

            # Transient server error — exponential backoff on current key
            elif "503" in error_msg or "429" in error_msg:
                rate_attempts += 1
                if rate_attempts > max_retries:
                    raise RuntimeError("Max retries reached on transient server errors.") from e
                wait_time = 45 * (2 ** (rate_attempts - 1))  # 45, 90, 180, 360, 720s
                print(f"Server busy (key {_key_index + 1}). Retrying in {wait_time}s "
                      f"(attempt {rate_attempts}/{max_retries})...")
                time.sleep(wait_time)

            else:
                raise

def get_z3_translation(theory, query):
    prompt = f"""
    Translate this logic puzzle into Python Z3 code.
    Theory: {theory}
    Query: {query}

   Rules:
    1. Start with 's = Solver()'
    2. Define entities as Bools, e.g., Yumpus = Bool('Yumpus')
    3. Use s.assert_and_track(condition, "Step_N")
    4. Assert the NEGATION of the query at the end.
    5. OUTPUT ONLY THE PYTHON CODE. NO TEXT. NO BACKTICKS.
    6. DO NOT write s.check() or evaluate the solver. We will do that.
    7. CRITICAL: Use snake_case variable names ONLY (e.g., Sam_is_Lorpus, Wren_is_Wumpus). NEVER use CamelCase. Every variable used must be declared with Bool() first. Be 100% consistent — if you declare Sam_is_Lorpus, NEVER write SamIsLorpus or sam_is_lorpus anywhere else.
    8. CRITICAL: For "if-then" or "are" statements, you MUST use the Z3 Python function Implies(A, B). NEVER use the '=>' or '->' symbols.
    """

    try:
        text = _call_api(prompt)

        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("python"):
                text = text[6:]

        clean_code = text.strip()
        if "s = Solver()" in clean_code:
            clean_code = clean_code[clean_code.find("s = Solver()"):]

        return clean_code

    except Exception as e:
        return f"# API ERROR: {e}"

_Z3_BUILTINS = {
    "Solver", "Bool", "And", "Or", "Not", "Implies", "ForAll",
    "sat", "unsat", "SAT", "UNSAT", "s", "True", "False", "None",
}

def _repair_var_names(code):
    """Fix CamelCase/snake_case mismatches in LLM-generated Z3 code.

    Builds a lookup from every Bool-declared variable name (normalised to
    lowercase with underscores stripped), then replaces any identifier that
    maps to a declared name but was spelled differently.
    """
    declared = re.findall(r'^(\w+)\s*=\s*Bool\(', code, re.MULTILINE)
    if not declared:
        return code
    lookup = {name.replace('_', '').lower(): name for name in declared}

    def _fix(match):
        name = match.group(0)
        if name in _Z3_BUILTINS:
            return name
        canonical = lookup.get(name.replace('_', '').lower())
        return canonical if canonical and canonical != name else name

    return re.sub(r'\b[A-Za-z_]\w*\b', _fix, code)

def verify_logic(generated_code):
    exec_globals = {
        "Solver": Solver, "Bool": Bool, "And": And, "Or": Or,
        "Not": Not, "Implies": Implies, "ForAll": ForAll,
        "sat": sat, "unsat": unsat, "SAT": sat, "UNSAT": unsat
    }
    local_vars = {"s": Solver()}

    if "API ERROR" in generated_code:
        return generated_code

    # Fix common LLM spelling and casing mistakes
    generated_code = generated_code.replace("Impllies", "Implies").replace("implied", "Implies").replace("implies", "Implies")
    generated_code = _repair_var_names(generated_code)

    try:
        exec(generated_code, exec_globals, local_vars)
        s = local_vars['s']
        s.set(unsat_core=True)

        result = s.check()
        if result == unsat:
            return f"SUCCESS: Verified. Core: {s.unsat_core()}"
        else:
            return "FAILURE: Logic consistent but proof not found."
    except Exception as e:
        print("\n--- CRASHING LLM CODE ---")
        print(generated_code)
        print("-------------------------\n")
        return f"SYNTAX ERROR: {e}"

def generate_case_study(theory, query, unsat_core, gold_chain, pure_llm_baseline):
    prompt = f"""
    You are an AI research assistant writing a case study on neuro-symbolic reasoning.
    
    Original Theory: {theory}
    Query: {query}
    
    We have three pieces of data:
    1. GOLD STANDARD PROOF: {gold_chain}
    2. PURE LLM BASELINE: {pure_llm_baseline}
    3. HYBRID Z3 UNSAT CORE LABELS: {unsat_core}
    
    Please generate a "Pretty-Printed Case Study" with the following exactly formatted sections:
    
    ### 1. Verified Logical Chain
    Look at the HYBRID Z3 UNSAT CORE labels. Figure out which exact English sentences in the Original Theory they correspond to. 
    Write out the validated proof steps using the ACTUAL ENGLISH SENTENCES. Do not use the "Step_N" labels in your output.
    
    ### 2. Comparative Analysis
    Briefly compare the PURE LLM BASELINE to the GOLD STANDARD and our Verified Logical Chain. 
    Did the pure LLM hallucinate? Did it skip steps? How did the Z3 verification improve the faithfulness of the logic?
    
    ### 3. Graceful Degradation (Belief Revision)
    Identify one premise from the Verified Logical Chain to "relax" or remove. 
    State the new "partial valid prefix/derivation" that remains after removal.
    """
    
    try:
        return _call_api(prompt)
    except Exception as e:
        return f"Case study generation failed: {e}"

def get_pure_llm_baseline(theory, query):
    prompt = f"""
    Solve this logic puzzle step-by-step.
    Theory: {theory}
    Query: {query}
    Provide a numbered chain of thought leading to your conclusion.
    """
    try:
        return _call_api(prompt)
    except Exception as e:
        return f"Baseline failed: {e}"

def load_and_run(filepath, limit= 10): 
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    keys = list(data.keys())[:limit]
    all_results = {} 
    
    for i, key in enumerate(keys):
        print(f"\n--- Example {i+1}: {key} ---")
        target = data[key].get('test_example', data[key])
        theory = target.get('question', '')
        query = target.get('query', '')
        
        # IMPROVEMENT B: Map Gold Standard steps to Original Theory 'Step_N' indices
        raw_chain = target.get('chain_of_thought', [])
        true_chain = []
        if isinstance(raw_chain, list):
            # Split theory into sentences for mapping
            theory_sentences = [s.strip() for s in theory.split('.') if s.strip()]
            
            for step in raw_chain:
                step_clean = step.replace('.', '').strip().lower()
                found_idx = -1
                for idx, t_sent in enumerate(theory_sentences):
                    if step_clean == t_sent.replace('.', '').strip().lower():
                        found_idx = idx + 1
                        break
                
                if found_idx != -1:
                    true_chain.append(f"Step_{found_idx}: {step}")
                else:
                    true_chain.append(f"Derived: {step}")
        else:
            true_chain = "No true chain provided"
        
        
        # MISSING PIECE 1: Get the Pure LLM Baseline (Control Group)
        print("Gathering Pure LLM Baseline...")
        pure_llm_thought = get_pure_llm_baseline(theory, query)
        
        # 1. Translate for Hybrid System
        code = get_z3_translation(theory, query)
        
        # 2. Verify
        verdict = verify_logic(code)
        print(f"Hybrid Verdict: {verdict}")

        # 3. Generate Pretty-Printed Case Study Comparison
        case_study_text = "N/A - No core extracted."
        if "SUCCESS" in verdict:
            core_str = verdict.split("Core: ")[1]
            print("Generating comparative case study...")
            # We pass all 3 pieces of data into the new function
            case_study_text = generate_case_study(theory, query, core_str, true_chain, pure_llm_thought)
        
        # Save EVERYTHING to dictionary for the final report
        all_results[key] = {
            "theory": theory, 
            "query": query,
            "gold_standard_proof": true_chain,  # The actual answer
            "pure_llm_baseline": pure_llm_thought, # The LLM's blind guess
            "hybrid_z3_verdict": verdict,       # Our system's check
            "comparative_analysis": case_study_text # The new pretty-printed output
        }
        
        if i < len(keys) - 1:
            print("Waiting 30 seconds for API limits...")
            time.sleep(30) 
            
    # Save the final results
    with open('Results/1hop_AndElim_results.json', 'w') as f:
        json.dump(all_results, f, indent=4)
    print("\nData collection complete. Ready for report writing!")
    
if __name__ == "__main__":
    # Ensure this filename matches folder exactly
    load_and_run('data/1hop_AndElim_random_noadj.json')
