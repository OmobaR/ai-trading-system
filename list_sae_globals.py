import MetaTrader5 as mt5

def main():
    terminal_path = r"C:\MT5_Dev\MT5_Dev_Portable_SynthX\terminal64.exe"
    
    if not mt5.initialize(path=terminal_path):
        print("MT5 initialization failed")
        return
    
    print("Connected to MT5")
    
    # Try the modern API first
    try:
        all_vars = mt5.global_variables_get()
        if all_vars:
            sae_vars = [v for v in all_vars if "SAE_" in v.name]
            print(f"\nFound {len(sae_vars)} SAE_* variables:")
            for v in sae_vars[:20]:  # show first 20
                print(f"  {v.name} = {v.value}")
        else:
            print("No global variables found (using global_variables_get)")
    except AttributeError:
        # Fallback to older API
        print("global_variables_get not available, using older API")
        total = mt5.global_variable_total()
        print(f"Total globals: {total}")
        for i in range(total):
            name = mt5.global_variable_name(i)
            if "SAE_" in name:
                value = mt5.global_variable_get(name)
                print(f"  {name} = {value}")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()