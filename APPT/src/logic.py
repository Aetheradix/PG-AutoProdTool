import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from src import config
from src.models import SKUMeta, Demand, ProductionBatch, VariantInfo


class PlanEnricher:
    def __init__(self, master_data: Dict[str, SKUMeta], bulk_map: Dict[str, VariantInfo]):
        self.master_data = master_data
        self.bulk_map = bulk_map

        # Build a "Normalized" Map for fuzzy matching
        # Key: Cleaned Description String, Value: VariantInfo
        self.clean_bulk_map = {}
        for desc, variant in bulk_map.items():
            clean_key = self._normalize_text(desc)
            if clean_key:
                self.clean_bulk_map[clean_key] = variant

    def _normalize_text(self, text: str) -> str:
        """
        Removes noise words and spaces to create a comparison key.
        Ex: "H&S Daily Clean IN GST FC" -> "H&SDAILYCLEAN"
        """
        if not text: return ""
        t = str(text).upper()

        # Remove Noise Phrases defined in Config
        for noise in config.MATCHING_NOISE_WORDS:
            # We add spaces to ensure we don't kill words inside other words
            # e.g. remove " IN " but not "IN" inside "FINISH"
            # Regex \b matches word boundaries
            pattern = r'\b' + re.escape(noise) + r'\b'
            t = re.sub(pattern, '', t)

        # Remove all non-alphanumeric characters (spaces, dashes, &, etc.)
        t = re.sub(r'[^A-Z0-9]', '', t)
        return t

    def find_variant_for_demand(self, demand: Demand) -> Optional[VariantInfo]:
        original_desc = demand.description.strip()

        # 1. Try EXACT Match (Fastest)
        if original_desc in self.bulk_map:
            return self.bulk_map[original_desc]

        # 2. Try NORMALIZED Match (Ignores GST, FC, spaces)
        demand_clean = self._normalize_text(original_desc)
        if demand_clean in self.clean_bulk_map:
            return self.clean_bulk_map[demand_clean]

        # 3. Try "Startswith" Match (Fallback)
        # If Packing is "H&S Clean" and Master is "H&S Clean extra text..."
        # or vice versa.
        for key, variant in self.clean_bulk_map.items():
            if demand_clean in key or key in demand_clean:
                # Only trust if it's a significant match (length > 5 chars)
                if len(demand_clean) > 5:
                    return variant

        # 4. Special Rules
        desc_lower = original_desc.lower()
        for keyword in config.RULE_CLIMBAZOLE:
            if keyword in desc_lower:
                return VariantInfo(gcas="PREMIX_CLIMBAZOLE", weight_per_container=0)

        return None

    def calculate_msu(self, quantity: float, weight_per_container: float) -> float:
        if weight_per_container <= 0 or quantity <= 0: return 0.0
        return (quantity * weight_per_container) / config.MSU_UNIT_KG

    def select_system(self, demand: Demand, sku: SKUMeta, variant: VariantInfo) -> Tuple[str, float, float]:
        desc_lower = str(demand.description).lower()

        # RULE 1: CLIMBAZOLE
        for kw in config.RULE_CLIMBAZOLE:
            if kw in desc_lower:
                return ("1.25T", 180, 0.0)

        # MSU Calculation
        msu = self.calculate_msu(demand.quantity, variant.weight_per_container)

        # Size Determination
        target_size = "12T"
        if msu > 0 and msu < config.MSU_THRESHOLD_6T:
            target_size = "6T"

        # RULE 2: CONDITIONER
        for kw in config.RULE_CONDITIONER:
            if kw in desc_lower:
                return ("6T MMT", self._get_bct(sku, "6T MMT"), msu)

        # RULE 3: HC BASE
        for kw in config.RULE_HC_BASE:
            if kw in desc_lower:
                target_sys = f"{target_size} MMT"
                return (target_sys, self._get_bct(sku, target_sys), msu)

        # RULE 4: SHAMPOO (Default)
        tech_type = sku.tech_class if sku else "Single"
        target_tech = "FMT"
        if tech_type.lower() == "dual":
            target_tech = "MMT"

        target_sys = f"{target_size} {target_tech}"
        return (target_sys, self._get_bct(sku, target_sys), msu)

    def _get_bct(self, sku: SKUMeta, target_system: str) -> float:
        if not sku: return config.DEFAULT_DURATION
        if target_system in sku.bct_by_system:
            return sku.bct_by_system[target_system]

        size = target_system.split()[0]
        for sys_name, duration in sku.bct_by_system.items():
            if size in sys_name:
                return duration
        return config.DEFAULT_DURATION


class Scheduler:
    def __init__(self, enricher: PlanEnricher):
        self.enricher = enricher
        self.batches = []

    def run(self, demands: List[Demand]) -> List[ProductionBatch]:
        print(f"--- Processing {len(demands)} Demands ---")
        batch_id_counter = 1

        for d in demands:
            variant = self.enricher.find_variant_for_demand(d)
            gcas = variant.gcas if variant else "UNKNOWN"

            system = "System TBD"
            bct = config.DEFAULT_DURATION
            msu = 0.0

            if gcas == "PREMIX_CLIMBAZOLE":
                system = "1.25T"
                bct = 180
            else:
                sku = self.enricher.master_data.get(gcas)
                system, bct, msu = self.enricher.select_system(d, sku, variant if variant else VariantInfo("UNK"))

            start_dt = d.start_dt - timedelta(minutes=int(bct))
            shift = self._get_shift(start_dt)

            tech_type = "Single"
            if sku: tech_type = sku.tech_class

            batch = ProductionBatch(
                id=f"B{batch_id_counter:03d}",
                sku_code=gcas,
                system=system,
                shift=shift,
                start_dt=start_dt,
                end_dt=d.start_dt,
                duration_min=int(bct),
                linked_order=d.order_id,
                material=d.material_code,
                desc=d.description,
                total_msu=msu,
                line=d.line,
                tech_type=tech_type
            )
            self.batches.append(batch)
            batch_id_counter += 1

        return self.batches

    def _get_shift(self, dt: datetime) -> str:
        h = dt.hour
        if 7 <= h < 15:
            return "B"
        elif 15 <= h < 23:
            return "C"
        else:
            return "A"