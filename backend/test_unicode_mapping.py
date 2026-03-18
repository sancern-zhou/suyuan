"""
测试Unicode上标字段映射
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.utils.data_standardizer import get_data_standardizer


def test_unicode_mapping():
    """测试Unicode上标字段映射"""

    output_file = Path(__file__).parent / "unicode_mapping_test_result.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("Unicode Field Mapping Test\n")
        f.write("=" * 80 + "\n\n")

        standardizer = get_data_standardizer()

        # API返回的Unicode上标字段
        test_fields = [
            'SO4²⁻', 'NO₃⁻', 'NH₄⁺',
            'Ca²⁺', 'Mg²⁺', 'K⁺', 'Na⁺', 'Cl⁻',
            'Al³⁺', 'Fe³⁺'
        ]

        f.write("Checking Unicode superscript field mappings:\n")
        f.write("-" * 80 + "\n")

        mapped_count = 0
        unmapped_fields = []

        for field in test_fields:
            standard = standardizer._get_standard_field_name(field)
            in_pm_mapping = field in standardizer.pm_component_field_mapping

            if standard:
                f.write(f"  {field:20} -> {standard:10} (in_pm_mapping={in_pm_mapping})\n")
                mapped_count += 1
            else:
                f.write(f"  {field:20} -> NOT MAPPED\n")
                unmapped_fields.append(field)

        f.write("\n" + "=" * 80 + "\n")
        f.write(f"Summary:\n")
        f.write(f"  Total fields tested: {len(test_fields)}\n")
        f.write(f"  Mapped: {mapped_count}\n")
        f.write(f"  Unmapped: {len(unmapped_fields)}\n")

        if unmapped_fields:
            f.write(f"\nUnmapped fields:\n")
            for field in unmapped_fields:
                f.write(f"  {field}\n")
            f.write("\nPROBLEM: These Unicode fields are NOT in pm_component_field_mapping!\n")
            f.write("This is why components are empty after standardization.\n")
        else:
            f.write("\nAll Unicode fields are properly mapped.\n")

        f.write("=" * 80 + "\n")

    print(f"Results written to: {output_file}")
    print(f"Mapped: {mapped_count}/{len(test_fields)}")
    if unmapped_fields:
        print(f"PROBLEM: {len(unmapped_fields)} fields are NOT mapped!")


if __name__ == "__main__":
    test_unicode_mapping()
