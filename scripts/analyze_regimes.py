#scripts/analyze_regimes.py
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.database.redis_feature_store import UnifiedRegimeFeatureStore
import logging
import pandas as pd
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_market_regimes():
    """Comprehensive market regime analysis across all symbols"""
    redis_config = {
        'host': 'localhost',
        'port': 6379,
        'db': 0
    }
    
    # Test different regime models
    regime_models = ['basic', 'technical', 'nnfx', 'comprehensive']
    
    for regime_model in regime_models:
        print(f"\n🎯 ANALYZING WITH {regime_model.upper()} REGIME MODEL")
        print("=" * 70)
        
        store = UnifiedRegimeFeatureStore(redis_config, regime_model=regime_model)
        
        # Test symbols
        test_symbols = ["GainX 600", "PainX 400", "FlipX 1", "FX Vol 20", "TrendX 600"]
        
        # Get tactical allocation
        allocation = store.get_tactical_allocation(test_symbols)
        
        print(f"\n💰 TACTICAL ALLOCATION OVERVIEW:")
        print(f"  Dominant Regime: {allocation.regime}")
        print(f"  Risk Multiplier: {allocation.risk_multiplier:.2f}")
        print(f"  Confidence: {allocation.confidence:.1%}")
        
        print(f"\n  Strategy Weights:")
        for strategy, weight in allocation.strategy_weights.items():
            print(f"    {strategy:<15} {weight:>6.1%}")
        
        print(f"\n  Symbol Weights (Top 5):")
        sorted_weights = sorted(allocation.symbol_weights.items(), key=lambda x: x[1], reverse=True)[:5]
        for symbol, weight in sorted_weights:
            print(f"    {symbol:<15} {weight:>6.1%}")
        
        # Individual symbol analysis
        print(f"\n📊 INDIVIDUAL SYMBOL ANALYSIS:")
        print("-" * 70)
        
        for symbol in test_symbols:
            profile = store.get_symbol_regime_profile(symbol)
            stats = store.get_regime_statistics(symbol)
            current_regime = store.get_current_regime(symbol)
            
            print(f"\n🔍 {symbol}:")
            print(f"   Current Regime: {current_regime or 'Unknown'}")
            print(f"   Symbol Type: {profile.get('symbol_type', 'Unknown')}")
            print(f"   Regime Model: {profile.get('regime_model', 'Unknown')}")
            
            if stats:
                print(f"   Regime Stability: {stats.get('regime_stability', 0)*100:.1f}%")
                print(f"   Avg Confidence: {stats.get('avg_confidence', 0)*100:.1f}%")
                
                distribution = stats.get('regime_distribution', {})
                if distribution:
                    print("   Historical Distribution:")
                    for regime, percentage in list(distribution.items())[:3]:  # Top 3
                        print(f"     {regime:<20} {percentage*100:>5.1f}%")
            
            # Check for ML features
            ml_features = store.get_ml_features(symbol)
            if ml_features:
                enhanced_conf = ml_features.get('regime_confidence_enhanced')
                if enhanced_conf:
                    print(f"   Enhanced Confidence: {enhanced_conf*100:.1f}%")
                
                nnfx_signal = ml_features.get('nnfx_signal')
                if nnfx_signal and nnfx_signal != "HOLD":
                    print(f"   NNFX Signal: {nnfx_signal} (Confidence: {ml_features.get('signal_confidence', 0)*100:.1f}%)")
        
        # Training data statistics
        print(f"\n📚 ML TRAINING DATA STATISTICS:")
        print("-" * 40)
        training_stats = store.get_training_data_stats()
        print(f"  Total Records: {training_stats['total_records']}")
        print(f"  Total Symbols: {training_stats['total_symbols']}")
        
        if training_stats['records_per_symbol']:
            print(f"  Records per Symbol:")
            for symbol, count in list(training_stats['records_per_symbol'].items())[:5]:
                print(f"    {symbol:<15} {count:>4} records")
        
        if training_stats['records_per_model']:
            print(f"  Records per Model:")
            for model, count in training_stats['records_per_model'].items():
                print(f"    {model:<15} {count:>4} records")
        
        # Export features for one symbol
        print(f"\n💾 DATA EXPORT:")
        export_result = store.export_ml_features_to_csv(test_symbols[0], days=7)
        print(f"  {export_result}")

def analyze_probabilistic_regimes():
    """Analyze probabilistic regime detection models"""
    print(f"\n🎲 PROBABILISTIC REGIME DETECTION ANALYSIS")
    print("=" * 70)
    
    redis_config = {
        'host': 'localhost',
        'port': 6379,
        'db': 0
    }
    
    store = UnifiedRegimeFeatureStore(redis_config, regime_model='comprehensive')
    store.setup_probabilistic_regimes('hmm')
    
    test_symbols = ["GainX 600", "PainX 400"]
    
    for symbol in test_symbols:
        print(f"\n🔮 {symbol} - Probabilistic Analysis:")
        
        # Get extended history for probabilistic analysis
        history = store.get_regime_history(symbol, limit=100, extended=True)
        
        if len(history) >= 50:
            # Extract features for probabilistic modeling
            features_list = []
            for event in history:
                if 'volatility' in event and 'trend_strength' in event:
                    features_list.append([
                        event.get('volatility', 0),
                        event.get('trend_strength', 0),
                        event.get('volume_profile', 0)
                    ])
            
            if features_list:
                feature_matrix = np.array(features_list)
                
                # HMM analysis
                hmm_result = store.compute_probabilistic_regime(symbol, feature_matrix[-1], 'hmm')
                if hmm_result:
                    print(f"   HMM Regime: {hmm_result['regime']}")
                    print(f"   HMM Confidence: {hmm_result['confidence']:.1%}")
                
                # GMM volatility clustering
                volatility_result = store.detect_volatility_regimes(symbol)
                if volatility_result:
                    print(f"   GMM Volatility Regime: {volatility_result['current_regime']}")
                    print(f"   GMM Confidence: {volatility_result['confidence']:.1%}")
        
        # Regime transition analysis
        stats = store.get_regime_statistics(symbol, extended=True)
        if stats:
            stability = stats.get('regime_stability', 0) * 100
            if stability < 60:
                print(f"   ⚠️  High Regime Volatility: {stability:.1f}% stability")
            else:
                print(f"   ✅ Stable Regime Pattern: {stability:.1f}% stability")

def generate_regime_report():
    """Generate a comprehensive regime analysis report"""
    print(f"\n📋 COMPREHENSIVE REGIME ANALYSIS REPORT")
    print("=" * 70)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Basic regime analysis
    analyze_market_regimes()
    
    # Probabilistic analysis
    analyze_probabilistic_regimes()
    
    print(f"\n🎯 RECOMMENDATIONS:")
    print("=" * 70)
    
    redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
    store = UnifiedRegimeFeatureStore(redis_config, regime_model='comprehensive')
    
    test_symbols = ["GainX 600", "PainX 400", "FlipX 1", "FX Vol 20", "TrendX 600"]
    allocation = store.get_tactical_allocation(test_symbols)
    
    print(f"\n1. DOMINANT MARKET REGIME: {allocation.regime.upper()}")
    print(f"   • Risk Level: {'HIGH' if allocation.risk_multiplier > 0.7 else 'MEDIUM' if allocation.risk_multiplier > 0.4 else 'LOW'}")
    print(f"   • Confidence: {allocation.confidence:.1%}")
    
    print(f"\n2. STRATEGY ALLOCATION:")
    for strategy, weight in allocation.strategy_weights.items():
        if weight > 0.1:
            print(f"   • {strategy.upper()}: {weight:.1%} allocation")
    
    print(f"\n3. SYMBOL RECOMMENDATIONS:")
    sorted_symbols = sorted(allocation.symbol_weights.items(), key=lambda x: x[1], reverse=True)
    for symbol, weight in sorted_symbols[:3]:
        profile = store.get_symbol_regime_profile(symbol)
        current_regime = store.get_current_regime(symbol)
        print(f"   • {symbol}: {weight:.1%} weight | Regime: {current_regime}")
    
    print(f"\n4. RISK MANAGEMENT:")
    if allocation.risk_multiplier > 0.8:
        print("   • ⚠️  Consider reducing position sizes due to high risk environment")
    elif allocation.risk_multiplier < 0.4:
        print("   • ✅ Favorable conditions for position sizing")
    
    print(f"\n5. MONITORING ALERTS:")
    for symbol in test_symbols:
        stats = store.get_regime_statistics(symbol)
        if stats and stats.get('regime_stability', 0) < 0.5:
            print(f"   • 🔄 {symbol}: High regime volatility detected")

if __name__ == "__main__":
    try:
        generate_regime_report()
        print(f"\n✅ Regime analysis completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during regime analysis: {e}")
        logger.error(f"Regime analysis failed: {e}")