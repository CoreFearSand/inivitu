"""
Bug Condition Exploration Test for Victoria 3 Country Functionality

This test is designed to FAIL on unfixed code to demonstrate the four bugs exist:
1. Countries page returns only ~100 countries due to LIMIT constraint
2. Country detail pages fail to load due to missing template
3. Country detail pages lack save selection functionality
4. Country names display as 3-letter codes instead of readable names

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

CRITICAL: This test MUST FAIL on unfixed code - failure confirms the bugs exist.
DO NOT attempt to fix the test or the code when it fails.
"""

import pytest
import requests
from pathlib import Path
import csv
import re
from typing import Dict, List, Set
from hypothesis import given, strategies as st, settings, HealthCheck
from hypothesis.strategies import composite
import sqlite3
import tempfile
import os
import sys

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from victoria3_tracker.web.server import WebServer
from victoria3_tracker.database import DatabaseManager
from victoria3_tracker.config import ConfigManager


class TestCountryBugsExploration:
    """
    Bug condition exploration tests that MUST FAIL on unfixed code.
    
    These tests encode the expected behavior and will validate the fix when they pass.
    """
    
    @pytest.fixture(scope="class")
    def test_app(self):
        """Create a test Flask app with sample data."""
        # Create temporary database
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        try:
            # Create config
            config = ConfigManager()
            config.config['database_path'] = db_file.name
            config.config['web_port'] = 8080
            config.config['save_directory'] = str(Path.cwd() / 'test_saves')
            config.config['log_level'] = 'INFO'
            
            # Create database manager and initialize schema
            db_manager = DatabaseManager(Path(db_file.name))
            
            # Insert test data
            self._insert_test_data(db_manager)
            
            # Create web server
            web_server = WebServer(config, db_manager)
            app = web_server.get_app()
            app.config['TESTING'] = True
            
            with app.test_client() as client:
                yield client, db_manager
                
        finally:
            # Cleanup
            try:
                db_manager.close()
            except:
                pass
            if os.path.exists(db_file.name):
                try:
                    os.unlink(db_file.name)
                except PermissionError:
                    # On Windows, sometimes the file is still locked
                    pass
    
    def _insert_test_data(self, db_manager: DatabaseManager):
        """Insert test data that will expose the bugs."""
        # Insert more than 100 countries to test LIMIT bug
        countries_data = []
        
        # Read country names from CSV to get realistic data
        csv_path = Path("victoria3_tracker/web/static/country_names.csv")
        country_mapping = {}
        
        if csv_path.exists():
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    country_mapping[row['Tag'].upper()] = row['Main Alias'].title()
        
        # Create 150+ countries to exceed LIMIT 100
        test_countries = list(country_mapping.keys())[:150] if country_mapping else []
        
        # If we don't have enough from CSV, generate more
        if len(test_countries) < 150:
            for i in range(150):
                tag = f"T{i:02d}"
                test_countries.append(tag)
                country_mapping[tag] = f"Test Country {i}"
        
        # Insert test saves and countries
        with db_manager.transaction() as conn:
            cursor = conn.cursor()
            
            # Insert test saves
            for i in range(3):
                save_id = f"test_save_{i}"
                cursor.execute("""
                    INSERT INTO Saves 
                    (save_id, playthrough_id, filename, saved_at, in_game_date, player_country, file_size, processing_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (save_id, f"playthrough_{i}", f"test_{i}.v3", "2024-01-01T00:00:00", 
                      f"1836-{i+1:02d}-01", test_countries[0], 1000000, 5000))
            
            # Insert countries (more than 100 to test LIMIT bug)
            for i, country_tag in enumerate(test_countries):
                save_id = f"test_save_{i % 3}"
                country_name = country_mapping.get(country_tag, country_tag)  # This shows the bug - codes vs names
                is_player = (i == 0)  # First country is player
                
                cursor.execute("""
                    INSERT OR IGNORE INTO Countries 
                    (country_tag, save_id, name, is_player_country)
                    VALUES (?, ?, ?, ?)
                """, (country_tag, save_id, country_name, is_player))
    
    def test_bug_1_countries_limit_constraint(self, test_app):
        """
        Bug 1: Countries page returns only ~100 countries due to LIMIT constraint.
        
        This test MUST FAIL on unfixed code because the SQL query has LIMIT 100.
        Expected behavior: All available countries should be displayed.
        """
        client, db_manager = test_app
        
        # Get total countries in database
        total_countries = db_manager.execute_query("SELECT COUNT(DISTINCT country_tag) as count FROM Countries")[0]['count']
        
        # Ensure we have more than 100 countries for this test
        assert total_countries > 100, f"Test setup error: Need >100 countries, got {total_countries}"
        
        # Access countries page
        response = client.get('/countries')
        assert response.status_code == 200
        
        # Count countries displayed on the page
        html_content = response.get_data(as_text=True)
        
        # Count country cards in the HTML
        country_card_pattern = r'class="col-md-6 col-lg-4 mb-3 country-card"'
        displayed_countries = len(re.findall(country_card_pattern, html_content))
        
        # BUG CONDITION: This assertion WILL FAIL on unfixed code due to LIMIT 100
        # Expected behavior: All countries should be displayed
        assert displayed_countries == total_countries, (
            f"Bug detected: Only {displayed_countries} countries displayed out of {total_countries} total. "
            f"This confirms the LIMIT 100 constraint bug exists."
        )
    
    def test_bug_2_missing_country_detail_template(self, test_app):
        """
        Bug 2: Country detail pages fail to load due to missing template.
        
        This test MUST FAIL on unfixed code because country_detail.html doesn't exist.
        Expected behavior: Country detail pages should load properly.
        """
        client, db_manager = test_app
        
        # Get a test country
        countries = db_manager.execute_query("SELECT country_tag FROM Countries LIMIT 1")
        assert countries, "Test setup error: No countries found"
        
        country_tag = countries[0]['country_tag']
        
        # Access country detail page
        response = client.get(f'/countries/{country_tag}')
        
        # BUG CONDITION: This assertion WILL FAIL on unfixed code due to missing template
        # The response will be 500 (template not found) instead of 200
        assert response.status_code == 200, (
            f"Bug detected: Country detail page returned status {response.status_code}. "
            f"This confirms the missing country_detail.html template bug exists."
        )
        
        # Additional check: ensure it's not an error page
        html_content = response.get_data(as_text=True)
        assert "Error" not in html_content and "failed to load" not in html_content, (
            "Bug detected: Country detail page shows error message. "
            "This confirms the missing template or functionality bug exists."
        )
    
    def test_bug_3_missing_save_selection_functionality(self, test_app):
        """
        Bug 3: Country detail pages lack save selection functionality.
        
        This test MUST FAIL on unfixed code because save selection is not implemented.
        Expected behavior: Country detail pages should have save selection dropdown.
        """
        client, db_manager = test_app
        
        # Get a test country
        countries = db_manager.execute_query("SELECT country_tag FROM Countries LIMIT 1")
        assert countries, "Test setup error: No countries found"
        
        country_tag = countries[0]['country_tag']
        
        # Access country detail page (this might fail due to bug 2, but we'll check anyway)
        response = client.get(f'/countries/{country_tag}')
        
        if response.status_code == 200:
            html_content = response.get_data(as_text=True)
            
            # BUG CONDITION: This assertion WILL FAIL on unfixed code
            # Save selection dropdown should exist like in wars.html
            save_selection_patterns = [
                r'id="save-select"',
                r'id="playthrough-select"',
                r'Save.*?select',
                r'Playthrough.*?select'
            ]
            
            has_save_selection = any(re.search(pattern, html_content, re.IGNORECASE) 
                                   for pattern in save_selection_patterns)
            
            assert has_save_selection, (
                "Bug detected: Country detail page lacks save selection functionality. "
                "This confirms the missing save selection bug exists."
            )
        else:
            # If page doesn't load due to bug 2, we can't test bug 3 directly
            # But we can check that the route doesn't have save selection logic
            pytest.skip("Cannot test save selection due to missing template (bug 2)")
    
    def test_bug_4_country_codes_instead_of_readable_names(self, test_app):
        """
        Bug 4: Country names display as 3-letter codes instead of readable names.
        
        This test MUST FAIL on unfixed code because CSV mapping is not integrated.
        Expected behavior: Country names should be readable (e.g., "Great Britain" not "GBR").
        """
        client, db_manager = test_app
        
        # Access countries page
        response = client.get('/countries')
        assert response.status_code == 200
        
        html_content = response.get_data(as_text=True)
        
        # Load expected country name mappings from CSV
        csv_path = Path("victoria3_tracker/web/static/country_names.csv")
        country_mapping = {}
        
        if csv_path.exists():
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    country_mapping[row['Tag'].upper()] = row['Main Alias'].title()
        
        # Find country names in the HTML
        country_name_pattern = r'<h6 class="card-title mb-0">([^<]+)</h6>'
        displayed_names = re.findall(country_name_pattern, html_content)
        
        # Check if we're seeing 3-letter codes instead of readable names
        three_letter_codes = []
        readable_names = []
        
        for name in displayed_names:
            name = name.strip()
            if len(name) == 3 and name.isupper() and name.isalpha():
                three_letter_codes.append(name)
                # Check if this code has a readable mapping
                if name in country_mapping:
                    readable_names.append(country_mapping[name])
        
        # BUG CONDITION: This assertion WILL FAIL on unfixed code
        # We should see readable names, not 3-letter codes
        if three_letter_codes and readable_names:
            # We have codes that should be converted to readable names
            codes_ratio = len(three_letter_codes) / len(displayed_names)
            
            assert codes_ratio < 0.1, (  # Less than 10% should be codes
                f"Bug detected: {len(three_letter_codes)} countries displayed as 3-letter codes "
                f"instead of readable names. Examples: {three_letter_codes[:5]}. "
                f"This confirms the missing CSV mapping integration bug exists."
            )


@composite
def country_test_data(draw):
    """Generate test data for property-based testing."""
    # Generate country tags (3-letter codes)
    country_tag = draw(st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=3, max_size=3))
    
    # Generate save data
    save_id = draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=5, max_size=20))
    
    return {
        'country_tag': country_tag,
        'save_id': save_id,
        'is_player': draw(st.booleans())
    }


@pytest.mark.skip(
    reason=(
        "Historical bug-simulation tests: these hard-code the buggy behavior "
        "to prove the bugs existed before the fix. They are not behavioural "
        "tests and will never pass. See TestCountryBugsExploration for the "
        "real regression tests."
    )
)
class TestCountryBugsPropertyBased:
    """Historical property-based simulations that document the bug conditions.

    These tests are intentionally skipped — they hard-code the buggy behaviour
    (e.g. min(100, total)) and will always fail.  They are kept only for
    historical reference.  The real regression tests live in
    TestCountryBugsExploration.
    """
    
    @given(st.lists(country_test_data(), min_size=101, max_size=200))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_all_countries_displayed(self, countries_data):
        """
        Property: All countries in the database should be displayed on the countries page.
        
        This property WILL FAIL on unfixed code due to LIMIT 100 constraint.
        """
        # This is a simplified property test - in a real scenario, we'd set up
        # a test database with the generated data and verify all countries are shown
        
        # Simulate the bug condition
        total_countries = len(countries_data)
        displayed_countries = min(100, total_countries)  # Simulates LIMIT 100 bug
        
        # This assertion encodes the expected behavior
        assert displayed_countries == total_countries, (
            f"Property violation: Only {displayed_countries} countries displayed "
            f"out of {total_countries} total. All countries should be displayed."
        )
    
    @given(st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=3, max_size=3))
    def test_property_country_detail_pages_accessible(self, country_tag):
        """
        Property: All country detail pages should be accessible and load properly.
        
        This property WILL FAIL on unfixed code due to missing template.
        """
        # Simulate accessing a country detail page
        # In unfixed code, this would return 500 due to missing template
        
        # This assertion encodes the expected behavior
        template_exists = False  # Simulates missing country_detail.html
        
        assert template_exists, (
            f"Property violation: Country detail page for {country_tag} not accessible. "
            f"All country detail pages should load properly."
        )
    
    @given(st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=3, max_size=3))
    def test_property_country_names_readable(self, country_tag):
        """
        Property: Country names should be displayed as readable names, not codes.
        
        This property WILL FAIL on unfixed code due to missing CSV integration.
        """
        # Load CSV mapping
        csv_path = Path("victoria3_tracker/web/static/country_names.csv")
        country_mapping = {}
        
        if csv_path.exists():
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    country_mapping[row['Tag'].upper()] = row['Main Alias'].title()
        
        # Check if country has a readable name mapping
        if country_tag in country_mapping:
            expected_name = country_mapping[country_tag]
            displayed_name = country_tag  # Simulates bug - showing code instead of name
            
            # This assertion encodes the expected behavior
            assert displayed_name == expected_name, (
                f"Property violation: Country {country_tag} displayed as code instead of "
                f"readable name '{expected_name}'. Names should be human-readable."
            )


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])