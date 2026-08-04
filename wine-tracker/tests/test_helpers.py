"""
Unit tests for pure helper functions in app.py.
These tests don't need Flask request context (where possible).
"""
import os
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
sys.path.insert(0, APP_DIR)

import app as wine_app


# ── load_options() ────────────────────────────────────────────────────────────

class TestLoadOptions:
    def test_defaults_when_file_missing(self, monkeypatch):
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", "/nonexistent/options.json")
        opts = wine_app.load_options()
        assert opts["currency"] == "CHF"
        assert opts["language"] == "de"
        assert opts["ai_provider"] == "none"

    def test_loads_from_json(self, tmp_path, monkeypatch):
        opts_file = tmp_path / "options.json"
        opts_file.write_text('{"currency": "EUR", "language": "en"}')
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", str(opts_file))
        opts = wine_app.load_options()
        assert opts["currency"] == "EUR"
        assert opts["language"] == "en"
        # Defaults still present for unset keys
        assert opts["ai_provider"] == "none"

    def test_backward_compat_anthropic_autodetect(self, tmp_path, monkeypatch):
        opts_file = tmp_path / "options.json"
        opts_file.write_text('{"anthropic_api_key": "sk-test-123"}')
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", str(opts_file))
        opts = wine_app.load_options()
        assert opts["ai_provider"] == "anthropic"

    def test_invalid_json_uses_defaults(self, tmp_path, monkeypatch):
        opts_file = tmp_path / "options.json"
        opts_file.write_text("{broken json")
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", str(opts_file))
        opts = wine_app.load_options()
        assert opts["currency"] == "CHF"


# ── _is_ai_configured() ──────────────────────────────────────────────────────

class TestIsAiConfigured:
    def test_none_provider(self):
        assert wine_app._is_ai_configured({"ai_provider": "none"}) is False

    def test_anthropic_with_key(self):
        assert wine_app._is_ai_configured(
            {"ai_provider": "anthropic", "anthropic_api_key": "sk-123"}
        ) is True

    def test_anthropic_without_key(self):
        assert wine_app._is_ai_configured(
            {"ai_provider": "anthropic", "anthropic_api_key": ""}
        ) is False

    def test_openai_with_key(self):
        assert wine_app._is_ai_configured(
            {"ai_provider": "openai", "openai_api_key": "sk-456"}
        ) is True

    def test_openrouter_with_key(self):
        assert wine_app._is_ai_configured(
            {"ai_provider": "openrouter", "openrouter_api_key": "or-789"}
        ) is True

    def test_ollama_with_host(self):
        assert wine_app._is_ai_configured(
            {"ai_provider": "ollama", "ollama_host": "http://localhost:11434"}
        ) is True

    def test_ollama_empty_host(self):
        assert wine_app._is_ai_configured(
            {"ai_provider": "ollama", "ollama_host": ""}
        ) is False

    def test_unknown_provider(self):
        assert wine_app._is_ai_configured({"ai_provider": "unknown"}) is False

    def test_whitespace_in_key(self):
        assert wine_app._is_ai_configured(
            {"ai_provider": "anthropic", "anthropic_api_key": "   "}
        ) is False


# ── allowed() ─────────────────────────────────────────────────────────────────

class TestAllowed:
    @pytest.mark.parametrize("filename,expected", [
        ("photo.jpg", True),
        ("photo.jpeg", True),
        ("photo.png", True),
        ("photo.webp", True),
        ("photo.gif", True),
        ("photo.JPG", True),      # case-insensitive
        ("photo.bmp", False),
        ("photo.svg", False),
        ("photo", False),          # no extension
        (".jpg", True),            # edge case: dot + ext
        ("photo.txt", False),
        ("photo.pdf", False),
    ])
    def test_allowed_extensions(self, filename, expected):
        assert wine_app.allowed(filename) == expected


# ── geocode_region() ──────────────────────────────────────────────────────────

class TestGeocodeRegion:
    def test_none_input(self):
        assert wine_app.geocode_region(None) is None

    def test_empty_string(self):
        assert wine_app.geocode_region("") is None

    def test_exact_match(self):
        coords = wine_app.geocode_region("Bordeaux")
        assert coords is not None
        assert isinstance(coords, list)
        assert len(coords) == 2

    def test_case_insensitive(self):
        c1 = wine_app.geocode_region("bordeaux")
        c2 = wine_app.geocode_region("BORDEAUX")
        c3 = wine_app.geocode_region("Bordeaux")
        assert c1 == c2 == c3

    def test_country_match(self):
        assert wine_app.geocode_region("Frankreich") is not None
        assert wine_app.geocode_region("France") is not None

    def test_substring_match(self):
        # "Toskana, Italien" should find "toskana"
        coords = wine_app.geocode_region("Toskana, Italien")
        assert coords is not None

    def test_unknown_region(self):
        assert wine_app.geocode_region("Planet Mars") is None


# ── format_date_filter() ──────────────────────────────────────────────────────

class TestFormatDate:
    def test_empty_value(self, app):
        with app.app_context():
            assert wine_app.format_date_filter("") == ""
            assert wine_app.format_date_filter(None) == ""

    def test_valid_date_german(self, app, monkeypatch):
        monkeypatch.setattr(wine_app, "LANG", "de")
        with app.app_context():
            result = wine_app.format_date_filter("2024-03-15")
            assert result == "15.03.2024"

    def test_valid_date_english(self, app, monkeypatch):
        monkeypatch.setattr(wine_app, "LANG", "en")
        with app.app_context():
            result = wine_app.format_date_filter("2024-03-15")
            assert result == "03/15/2024"

    def test_invalid_date(self, app):
        with app.app_context():
            assert wine_app.format_date_filter("not-a-date") == "not-a-date"


# ── translate_wine_type() ─────────────────────────────────────────────────────

class TestTranslateWineType:
    def test_known_type(self, app, monkeypatch):
        from translations import TRANSLATIONS
        monkeypatch.setattr(wine_app, "T", TRANSLATIONS["en"])
        with app.app_context():
            result = wine_app.translate_wine_type("Rotwein")
            assert result == "Red Wine"

    def test_unknown_type_passthrough(self, app):
        with app.app_context():
            assert wine_app.translate_wine_type("UnknownType") == "UnknownType"


# ── _wine_json_schema() / _wine_json_rules() ─────────────────────────────────

class TestWineJsonSchema:
    def test_schema_contains_all_fields(self):
        schema = wine_app._wine_json_schema()
        # `notes` is deliberately absent - it belongs to the user, the AI writes
        # `description` instead. See TestAiNeverWritesNotes.
        for field in ["name", "winery", "region", "grape", "grapes", "price", "description"]:
            assert field in schema

    def test_schema_omits_bottle_format(self):
        """The user owns the physical bottle - AI must not set its format."""
        assert "bottle_format" not in wine_app._wine_json_schema()
        assert "bottle_format" not in wine_app._wine_json_rules("de")

    def test_rules_request_the_configured_currency(self):
        rules = wine_app._wine_json_rules("de", "EUR")
        assert "EUR" in rules


class TestAiScopes:
    """A scoped refresh must ask for its fields only - both in the schema and in
    the ruleset, so the model has neither the slots nor the instructions to
    rewrite anything else."""

    def test_price_scope_asks_only_for_the_price(self):
        s = wine_app._wine_json_schema("wine", "price")
        assert '"price"' in s and '"ai_rationale"' in s
        for gone in ("vintage", "grapes", "maturity_data", "taste_profile", "notes", "winery"):
            assert gone not in s, gone

    def test_profile_scope_asks_only_for_estimates(self):
        s = wine_app._wine_json_schema("wine", "profile")
        for want in ("drink_from", "drink_until", "maturity_data",
                     "taste_profile", "food_pairings"):
            assert want in s, want
        for gone in ("vintage", "grapes", "price", "winery", "region"):
            assert gone not in s, gone

    def test_spirit_profile_scope_is_the_taste_profile(self):
        s = wine_app._wine_json_schema("whisky", "profile")
        assert "taste_profile" in s
        # a whisky has no drinking window or maturity phases
        for gone in ("maturity_data", "drink_from", "food_pairings", "abv", "casks"):
            assert gone not in s, gone

    def test_all_scope_is_unchanged(self):
        assert (wine_app._wine_json_schema("wine", "all")
                == wine_app._wine_json_schema("wine"))
        s = wine_app._wine_json_schema("wine", "all")
        for want in ("name", "winery", "vintage", "grapes", "price", "maturity_data"):
            assert want in s, want

    def test_unknown_scope_falls_back_to_all(self):
        assert (wine_app._wine_json_schema("wine", "nonsense")
                == wine_app._wine_json_schema("wine", "all"))

    def test_scoped_rules_drop_unrelated_instructions(self):
        rules = wine_app._wine_json_rules("de", "CHF", "wine", "price")
        assert "CHF" in rules
        assert "maturity_data" not in rules
        assert "food_pairings" not in rules
        # and it is told explicitly not to volunteer anything else
        assert "Return ONLY the listed keys" in rules

    def test_full_rules_keep_every_instruction(self):
        rules = wine_app._wine_json_rules("de", "CHF", "wine", "all")
        for want in ("maturity_data", "food_pairings", "drink_from", "grapes"):
            assert want in rules, want
        assert "Return ONLY the listed keys" not in rules

    def test_profile_rules_do_not_mention_the_price(self):
        rules = wine_app._wine_json_rules("de", "CHF", "wine", "profile")
        assert "retail bottle price" not in rules

    def test_scoped_call_drops_the_image_and_uses_its_own_task_wording(self, monkeypatch):
        """A price lookup is a search task: the label photo only costs tokens and
        tempts the model into re-identifying the bottle."""
        captured = {}

        def fake_call(image_b64, media_type, prompt, opts):
            captured["image"] = image_b64
            captured["prompt"] = prompt
            return '{"price": 42}'

        monkeypatch.setattr(wine_app, "_call_openai", fake_call)
        opts = {"ai_provider": "openai", "openai_api_key": "k", "currency": "CHF",
                "openai_web_search": False}
        wine_app._analyze_wine_from_context(
            opts, "ZmFrZQ==", "image/jpeg", {"name": "Barolo", "category": "wine"}, "price")
        assert captured["image"] is None
        assert "retail price" in captured["prompt"]
        assert "bottle label image" not in captured["prompt"]

    def test_profile_prompt_forbids_re_identifying(self, monkeypatch):
        captured = {}
        def grab(i, m, prompt, o):
            captured["p"] = prompt
            return "{}"

        monkeypatch.setattr(wine_app, "_call_openai", grab)
        opts = {"ai_provider": "openai", "openai_api_key": "k", "currency": "CHF",
                "openai_web_search": False}
        wine_app._analyze_wine_from_context(
            opts, None, None, {"name": "Barolo", "category": "wine"}, "profile")
        assert "Do NOT re-identify" in captured["p"]
        assert "drinking window" in captured["p"]

    def test_spirit_profile_prompt_talks_about_taste_only(self, monkeypatch):
        captured = {}
        def grab(i, m, prompt, o):
            captured["p"] = prompt
            return "{}"

        monkeypatch.setattr(wine_app, "_call_openai", grab)
        opts = {"ai_provider": "openai", "openai_api_key": "k", "currency": "CHF",
                "openai_web_search": False}
        wine_app._analyze_wine_from_context(
            opts, None, None, {"name": "Lagavulin", "category": "whisky"}, "profile")
        assert "taste profile" in captured["p"]
        assert "whisky" in captured["p"] and "drinking window" not in captured["p"]

    def test_scope_keys(self):
        assert wine_app._scope_keys("wine", "all") is None
        assert wine_app._scope_keys("wine", "price") == ("price",)
        assert "maturity_data" in wine_app._scope_keys("wine", "profile")
        assert wine_app._scope_keys("whisky", "profile") == ("taste_profile",)


class TestAiNeverWritesNotes:
    """`notes` is the user's field. The AI is not offered it anywhere - not in a
    schema, not in a rule, not in the chat action format."""

    @pytest.mark.parametrize("category", ["wine", "whisky", "spirit"])
    @pytest.mark.parametrize("scope", ["all", "price", "profile"])
    def test_no_schema_ever_requests_notes(self, category, scope):
        assert '"notes"' not in wine_app._wine_json_schema(category, scope)

    @pytest.mark.parametrize("category", ["wine", "whisky"])
    def test_full_schema_requests_a_description(self, category):
        assert '"description"' in wine_app._wine_json_schema(category, "all")

    def test_rules_forbid_returning_notes(self):
        rules = wine_app._wine_json_rules("de", "CHF", "wine", "all")
        assert 'NEVER return a "notes" field' in rules
        assert "- description:" in rules

    def test_description_is_requested_in_the_configured_language(self):
        assert "German" in wine_app._wine_json_rules("de", "CHF", "wine", "all")
        assert "Italian" in wine_app._wine_json_rules("it", "CHF", "wine", "all")

    def test_scan_schema_asks_for_a_description_not_notes(self):
        """The label-scan prompt is built separately from the reload schema."""
        import re
        src = open(os.path.join(APP_DIR, "app.py"), encoding="utf-8").read()
        block = re.search(r'"wine name \(without the producer\)".*?food_pairings', src, re.S)
        assert block, "scan schema block not found"
        assert '"notes"' not in block.group(0)
        assert '"description"' in block.group(0)

    def test_chat_add_uses_description_and_guards_notes(self):
        src = open(os.path.join(APP_DIR, "app.py"), encoding="utf-8").read()
        assert '"description": "2-3 sentences about style, aroma and taste"' in src
        assert '"notes": "Tasting notes"' not in src
        # the guard text; matched without the apostrophe, which is escaped in the source
        assert "own field. Only ever set it when the user explicitly" in src
        assert "Never put a" in src and "tasting description there" in src


class TestPriceMarket:
    """A price from a foreign shop is the wrong answer even when it is correct.
    There is no country option, so the market is derived from currency+language."""

    @pytest.mark.parametrize("currency,lang,country,tld", [
        ("CHF", "de", "Switzerland", ".ch"),
        ("GBP", "en", "the United Kingdom", ".co.uk"),
        ("USD", "en", "the United States", ".com"),
        ("SEK", "sv", "Sweden", ".se"),
    ])
    def test_distinct_currency_decides_alone(self, currency, lang, country, tld):
        assert wine_app._price_market(currency, lang) == (country, tld)

    @pytest.mark.parametrize("lang,country", [
        ("de", "Germany or Austria"), ("fr", "France"), ("it", "Italy"),
        ("es", "Spain"), ("pt", "Portugal"), ("nl", "the Netherlands or Belgium"),
    ])
    def test_language_decides_inside_the_euro_zone(self, lang, country):
        assert wine_app._price_market("EUR", lang)[0] == country

    def test_lowercase_and_padded_currency(self):
        assert wine_app._price_market(" chf ", "de")[0] == "Switzerland"

    def test_unknown_currency_has_no_market(self):
        assert wine_app._price_market("XYZ", "en") is None
        assert wine_app._price_market("", "en") is None
        assert wine_app._price_market(None, None) is None

    def test_unknown_euro_language_has_no_market(self):
        assert wine_app._price_market("EUR", "sv") is None

    def test_price_rule_names_the_local_market_first(self):
        rule = [l for l in wine_app._wine_json_rules("de", "CHF", "wine", "price").split("\n")
                if l.startswith("- price")][0]
        assert "shops located in Switzerland FIRST" in rule
        assert ".ch domains" in rule
        # and it must still demand the target currency
        assert "in CHF" in rule

    def test_price_rule_is_a_single_instruction(self):
        """Two lines both starting with '- price:' read as competing rules."""
        rules = wine_app._wine_json_rules("de", "CHF", "wine", "price")
        assert len([l for l in rules.split("\n") if l.startswith("- price")]) == 1

    def test_local_market_applies_to_a_full_refresh_too(self):
        rules = wine_app._wine_json_rules("de", "CHF", "wine", "all")
        assert "shops located in Switzerland FIRST" in rules

    def test_unknown_currency_drops_the_hint_silently(self):
        rules = wine_app._wine_json_rules("en", "XYZ", "wine", "price")
        assert "FIRST" not in rules
        assert "in XYZ" in rules

    def test_spirits_get_the_same_market_preference(self):
        rules = wine_app._wine_json_rules("de", "CHF", "whisky", "price")
        assert "Switzerland" in rules

    def test_price_prompt_names_the_market_up_front(self, monkeypatch):
        captured = {}

        def grab(i, m, prompt, o):
            captured["p"] = prompt
            return '{"price": 42}'

        monkeypatch.setattr(wine_app, "_call_openai", grab)
        monkeypatch.setattr(wine_app, "LANG", "de")
        opts = {"ai_provider": "openai", "openai_api_key": "k", "currency": "CHF",
                "openai_web_search": False}
        wine_app._analyze_wine_from_context(
            opts, None, None, {"name": "Barolo", "category": "wine"}, "price")
        # the task line itself, before the rules, already points at the market
        task = captured["p"].split("Rules:")[0]
        assert "shops based in Switzerland first" in task
        assert ".ch domains" in task

    def test_price_prompt_without_a_known_market(self, monkeypatch):
        captured = {}

        def grab(i, m, prompt, o):
            captured["p"] = prompt
            return '{"price": 42}'

        monkeypatch.setattr(wine_app, "_call_openai", grab)
        opts = {"ai_provider": "openai", "openai_api_key": "k", "currency": "XYZ",
                "openai_web_search": False}
        wine_app._analyze_wine_from_context(
            opts, None, None, {"name": "Barolo", "category": "wine"}, "price")
        task = captured["p"].split("Rules:")[0]
        assert "current online shops and price comparison sites" in task


# ── ENV variable config override ─────────────────────────────────────────────

class TestEnvConfig:
    """Tests for ENV variable configuration override (standalone Docker)."""

    # All ENV keys that load_options() reads - clear them before each test
    _ENV_KEYS = [
        "CURRENCY", "LANGUAGE", "AI_PROVIDER",
        "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
        "OPENAI_API_KEY", "OPENAI_MODEL",
        "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
        "OLLAMA_HOST", "OLLAMA_MODEL",
    ]

    def _clear_env(self, monkeypatch):
        for key in self._ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

    def test_env_overrides_defaults(self, monkeypatch):
        """ENV vars should override built-in defaults when no options.json exists."""
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", "/nonexistent/options.json")
        self._clear_env(monkeypatch)
        monkeypatch.setenv("CURRENCY", "EUR")
        monkeypatch.setenv("LANGUAGE", "en")
        opts = wine_app.load_options()
        assert opts["currency"] == "EUR"
        assert opts["language"] == "en"

    def test_env_overrides_options_json(self, tmp_path, monkeypatch):
        """ENV vars should take precedence over options.json values."""
        opts_file = tmp_path / "options.json"
        opts_file.write_text('{"currency": "CHF", "language": "de"}')
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", str(opts_file))
        self._clear_env(monkeypatch)
        monkeypatch.setenv("CURRENCY", "USD")
        opts = wine_app.load_options()
        assert opts["currency"] == "USD"  # ENV wins
        assert opts["language"] == "de"   # options.json kept

    def test_options_json_still_works(self, tmp_path, monkeypatch):
        """options.json values should work when no ENV override is set."""
        opts_file = tmp_path / "options.json"
        opts_file.write_text('{"currency": "EUR"}')
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", str(opts_file))
        self._clear_env(monkeypatch)
        opts = wine_app.load_options()
        assert opts["currency"] == "EUR"

    def test_all_env_keys_mapped(self, monkeypatch):
        """All ENV keys in env_map should be applied correctly."""
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", "/nonexistent/options.json")
        self._clear_env(monkeypatch)
        monkeypatch.setenv("AI_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-5")
        opts = wine_app.load_options()
        assert opts["ai_provider"] == "openai"
        assert opts["openai_api_key"] == "sk-test-key"
        assert opts["openai_model"] == "gpt-5"

    def test_empty_env_does_not_override(self, tmp_path, monkeypatch):
        """Empty string ENV vars should not override options.json."""
        opts_file = tmp_path / "options.json"
        opts_file.write_text('{"currency": "CHF"}')
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", str(opts_file))
        self._clear_env(monkeypatch)
        # os.environ.get returns "" for empty string, but load_options
        # only overrides when val is truthy
        monkeypatch.setenv("CURRENCY", "")
        opts = wine_app.load_options()
        assert opts["currency"] == "CHF"  # empty ENV should not override


# ── View modal translations ─────────────────────────────────────────────────

class TestViewModalTranslations:
    def test_view_modal_translations_all_languages(self):
        """All 7 languages should have view modal translation keys."""
        from translations import TRANSLATIONS
        for lang in TRANSLATIONS:
            assert "modal_view_title" in TRANSLATIONS[lang], f"Missing modal_view_title in {lang}"
            assert "btn_close" in TRANSLATIONS[lang], f"Missing btn_close in {lang}"
            assert "view_drink_window" in TRANSLATIONS[lang], f"Missing view_drink_window in {lang}"


# ── Out-of-stock translations ────────────────────────────────────────────────

class TestOutOfStockTranslations:
    def test_out_of_stock_keys_in_all_languages(self):
        """All 7 languages need the out-of-stock ribbon and settings keys, non-empty."""
        from translations import TRANSLATIONS
        for lang in TRANSLATIONS:
            for key in ("ribbon_empty", "settings_show_empty"):
                assert key in TRANSLATIONS[lang], f"Missing {key} in {lang}"
                assert TRANSLATIONS[lang][key].strip(), f"Empty {key} in {lang}"


# ── parse_user_string / DEV_AUTH ─────────────────────────────────────────────

class TestParseUserString:
    """Tests for parse_user_string() used by AUTH_ENABLED and DEV_AUTH."""

    def test_single_user_default_role(self):
        """Single user without role should default to 'admin'."""
        from werkzeug.security import check_password_hash
        result = wine_app.parse_user_string("myuser:mypass")
        assert "myuser" in result
        assert result["myuser"]["role"] == "admin"
        assert check_password_hash(result["myuser"]["hash"], "mypass")

    def test_single_user_with_role(self):
        """Single user with explicit role should use that role."""
        result = wine_app.parse_user_string("viewer:secret:readonly")
        assert "viewer" in result
        assert result["viewer"]["role"] == "readonly"

    def test_multiple_users(self):
        """Comma-separated users should all be parsed."""
        result = wine_app.parse_user_string("admin:pass1:admin,viewer:pass2:readonly")
        assert len(result) == 2
        assert result["admin"]["role"] == "admin"
        assert result["viewer"]["role"] == "readonly"

    def test_empty_string(self):
        """Empty string should return empty dict."""
        result = wine_app.parse_user_string("")
        assert result == {}

    def test_whitespace_only(self):
        """Whitespace-only string should return empty dict."""
        result = wine_app.parse_user_string("   ")
        assert result == {}

    def test_strips_whitespace(self):
        """Whitespace around entries should be stripped."""
        result = wine_app.parse_user_string("  admin : pass : admin , viewer : pw : readonly  ")
        assert "admin" in result
        assert "viewer" in result
        assert result["admin"]["role"] == "admin"
        assert result["viewer"]["role"] == "readonly"

    def test_invalid_entry_skipped(self):
        """Entries without colon should be skipped."""
        result = wine_app.parse_user_string("valid:pass,invalidentry")
        assert len(result) == 1
        assert "valid" in result

    def test_password_hash_is_valid(self):
        """Parsed passwords should be properly hashed and verifiable."""
        from werkzeug.security import check_password_hash
        result = wine_app.parse_user_string("test:hunter2")
        assert check_password_hash(result["test"]["hash"], "hunter2")
        assert not check_password_hash(result["test"]["hash"], "wrongpass")


# ── _build_wine_cellar_context() ──────────────────────────────────────────────

class TestBuildWineCellarContext:
    """AI sommelier context must include the fields the chat CRUD feature needs."""

    def test_empty_cellar_returns_empty_string(self, app):
        with app.app_context():
            text, count = wine_app._build_wine_cellar_context()
        assert text == ""
        assert count == 0

    def test_includes_quantity_rating_and_location(self, app, sample_wine):
        """Chat CRUD needs quantity, rating and location to answer stock/search questions."""
        with app.app_context():
            text, count = wine_app._build_wine_cellar_context()
        assert count == 1
        assert "Château Test" in text
        # Context must carry data required for CRUD / search use cases
        assert "Menge: 3" in text
        assert "Bewertung: 4/5" in text
        assert "Lagerort: Keller A" in text

    def test_includes_id_for_crud_references(self, app, sample_wine):
        """IDs are required so the AI can reference a specific wine for CRUD ops."""
        wine_id = sample_wine["wine"]["id"]
        with app.app_context():
            text, _ = wine_app._build_wine_cellar_context()
        assert f"[ID:{wine_id}]" in text

    def test_skips_out_of_stock_wines(self, app, client, sample_wine):
        """Wines with quantity=0 should not appear in the AI context."""
        wine_id = sample_wine["wine"]["id"]
        # Drain the wine
        with app.app_context():
            db = wine_app.get_db()
            db.execute("UPDATE wines SET quantity = 0 WHERE id = ?", (wine_id,))
            db.commit()
            text, count = wine_app._build_wine_cellar_context()
        assert count == 0
        assert text == ""

    def test_respects_language_setting(self, app, sample_wine, monkeypatch):
        """Labels should follow the configured language."""
        monkeypatch.setattr(wine_app, "LANG", "en")
        with app.app_context():
            text, _ = wine_app._build_wine_cellar_context()
        assert "Quantity: 3 btl." in text
        assert "Rating: 4/5" in text
        assert "Location: Keller A" in text

    def test_falls_back_to_english_for_unknown_language(self, app, sample_wine, monkeypatch):
        monkeypatch.setattr(wine_app, "LANG", "xx")
        with app.app_context():
            text, _ = wine_app._build_wine_cellar_context()
        # English fallback applied
        assert "Vintage 2020" in text


# ── warn_missing_secret_key() ─────────────────────────────────────────────────

class TestSecretKeyWarning:
    def test_warns_when_auth_enabled_without_secret_key(self, monkeypatch, capsys):
        monkeypatch.setattr(wine_app, "AUTH_ENABLED", True)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        wine_app.warn_missing_secret_key()
        assert "SECRET_KEY" in capsys.readouterr().out

    def test_silent_when_secret_key_set(self, monkeypatch, capsys):
        monkeypatch.setattr(wine_app, "AUTH_ENABLED", True)
        monkeypatch.setenv("SECRET_KEY", "some-persistent-key")
        wine_app.warn_missing_secret_key()
        assert capsys.readouterr().out == ""

    def test_silent_when_auth_disabled(self, monkeypatch, capsys):
        monkeypatch.setattr(wine_app, "AUTH_ENABLED", False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        wine_app.warn_missing_secret_key()
        assert capsys.readouterr().out == ""


# ── Production server dependency ──────────────────────────────────────────────

class TestServerDependency:
    def test_waitress_is_available(self):
        """app.py serves via waitress in production - the import must work."""
        import waitress  # noqa: F401


def test_grape_names_from_ids():
    import app as wine_app
    gmap = {1: "Merlot", 2: "Cabernet Sauvignon"}
    assert wine_app._grape_names_from_ids(gmap, [1, 2, 99]) == ["Merlot", "Cabernet Sauvignon"]
    assert wine_app._grape_names_from_ids(gmap, []) == []


# ── AI JSON parsing (robust against fences / prose / truncation) ──────────────

class TestParseAiJson:
    def _f(self):
        import app as wine_app
        return wine_app._parse_ai_json

    def test_plain_json(self):
        assert self._f()('{"name": "Barolo"}') == {"name": "Barolo"}

    def test_code_fenced_json(self):
        assert self._f()('```json\n{"name": "Barolo"}\n```') == {"name": "Barolo"}

    def test_json_with_surrounding_prose(self):
        raw = 'Hier das Ergebnis:\n{"name": "Barolo"}\nQuelle: example.com'
        assert self._f()(raw) == {"name": "Barolo"}

    def test_empty_output_raises(self):
        import pytest as pt
        for bad in ("", "   ", None, "```json"):
            with pt.raises(ValueError, match="ai_bad_response"):
                self._f()(bad)

    def test_truncated_json_raises(self):
        import pytest as pt
        with pt.raises(ValueError, match="ai_bad_response"):
            self._f()('{"name": "Barolo", "region": "Piem')


# ── canonicalizing AI output against the reference lists ──────────────────────

class TestCanonicalizeAiFields:
    def _run(self, db, fields):
        import app as wine_app
        return wine_app._canonicalize_ai_fields(db, fields)

    def test_grape_alias_maps_to_canonical(self, db):
        out = self._run(db, {"grape": "Shiraz", "grapes": [{"name": "Shiraz", "pct": 100}]})
        assert out["grape"] == "Syrah"
        assert out["grapes"][0]["name"] == "Syrah"

    def test_country_alias_maps_to_canonical(self, db):
        out = self._run(db, {"country": "CH"})
        assert out["country"] not in ("", "CH")     # resolved to the ref name

    def test_unknown_values_are_left_alone(self, db):
        out = self._run(db, {"grape": "Hauswein XY", "region": "Irgendwo"})
        assert out["grape"] == "Hauswein XY"
        assert out["region"] == "Irgendwo"

    def test_empty_fields_survive(self, db):
        assert self._run(db, {})== {}


class TestSpiritAiSchema:
    def test_whisky_schema_has_spirit_fields(self):
        import app as wine_app
        s = wine_app._wine_json_schema("whisky")
        for f in ("abv", "age_years", "cask", "bottler", "batch_number", "peat_ppm"):
            assert f in s, f

    def test_whisky_schema_drops_wine_fields(self):
        import app as wine_app
        s = wine_app._wine_json_schema("whisky")
        for f in ("grapes", "maturity_data", "food_pairings", "drink_from"):
            assert f not in s, f

    def test_wine_schema_unchanged(self):
        import app as wine_app
        s = wine_app._wine_json_schema("wine")
        assert "grapes" in s and "abv" not in s

    def test_whisky_rules_mention_casks(self):
        import app as wine_app
        r = wine_app._wine_json_rules("de", "CHF", "whisky")
        assert "casks" in r and "CHF" in r
        assert "grapes:" not in r

    def test_valid_types_are_category_aware(self, db):
        import app as wine_app
        assert "Rotwein" in wine_app._valid_types(db, "wine")
        assert "Single Malt" in wine_app._valid_types(db, "whisky")
        assert "Single Malt" not in wine_app._valid_types(db, "wine")

    def test_cask_alias_is_canonicalized(self, db):
        import app as wine_app
        out = wine_app._canonicalize_ai_fields(
            db, {"casks": [{"name": "PX", "years": 2}]}, "whisky")
        assert out["casks"][0]["name"] == "PX Sherry"

    def test_spirit_type_alias_is_canonicalized(self, db):
        import app as wine_app
        out = wine_app._canonicalize_ai_fields(db, {"wine_type": "Vodka"}, "whisky")
        assert out["wine_type"] == "Wodka"

    def test_wine_canonicalization_unaffected(self, db):
        import app as wine_app
        out = wine_app._canonicalize_ai_fields(db, {"grape": "Shiraz"}, "wine")
        assert out["grape"] == "Syrah"

    def test_spirit_region_alias_is_canonicalized(self, db):
        import app as wine_app
        out = wine_app._canonicalize_ai_fields(
            db, {"region": "Orkney", "country": "United Kingdom"}, "whisky")
        assert out["region"] == "Islands"

    def test_wine_region_not_resolved_from_spirit_list(self, db):
        """A wine claiming to come from Orkney stays untouched - it is not a
        wine region, so the wine list has nothing to map it onto."""
        import app as wine_app
        out = wine_app._canonicalize_ai_fields(db, {"region": "Orkney"}, "wine")
        assert out["region"] == "Orkney"

    def test_map_coords_resolve_for_spirit_regions(self, db):
        import app as wine_app
        coords = wine_app.resolve_map_coords(db, "Islay", None, category="whisky")
        assert coords and round(coords[0], 1) == 55.8
        # the fallback finds it even when the category is not passed
        assert wine_app.resolve_map_coords(db, "Islay", None) == coords
