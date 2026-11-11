"""Dinamik səhifə: Selenium (dərs, bölmə 5). Real brauzer JavaScript-i icra edir, biz WebDriverWait ilə gözləyirik
(time.sleep deyil: səhifə 1 saniyədə də yüklənə bilər, 6 saniyədə də). driver.quit() HƏMİŞƏ çağırılır."""

import os

from app.parsing import detect_currency, parse_price
from app.scrapers.base import Item, ScrapeResult, SiteConfig


class DynamicScrapingUnavailable(Exception):
    pass


def scrape_selenium(cfg: SiteConfig, selenium_url: str = "", wait_seconds: int = 10, driver_factory=None) -> ScrapeResult:
    selenium_url = selenium_url or os.environ.get("SELENIUM_URL", "")
    if driver_factory is None and not selenium_url:
        raise DynamicScrapingUnavailable("SELENIUM_URL təyin olunmayıb. Başlat: docker compose --profile selenium up -d selenium, "
                                         "sonra SELENIUM_URL=http://selenium:4444/wd/hub")
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    if driver_factory is None:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        driver = webdriver.Remote(command_executor=selenium_url, options=options)
    else:
        driver = driver_factory()
    res = ScrapeResult(strategy="selenium", pages=1)
    try:
        driver.get(cfg.start_url)
        WebDriverWait(driver, wait_seconds).until(EC.presence_of_element_located((By.CSS_SELECTOR, cfg.wait_selector or cfg.item_selector)))
        for card in driver.find_elements(By.CSS_SELECTOR, cfg.item_selector):
            try:
                name_el = card.find_element(By.CSS_SELECTOR, cfg.name_selector)
                name = (name_el.get_attribute(cfg.name_attr) if cfg.name_attr else None) or name_el.text
                raw = card.find_element(By.CSS_SELECTOR, cfg.price_selector).text
                stock = ""
                if cfg.stock_selector:
                    els = card.find_elements(By.CSS_SELECTOR, cfg.stock_selector)
                    stock = els[0].text if els else ""
                res.items.append(Item(name=name.strip(), price=parse_price(raw), currency=detect_currency(raw, cfg.default_currency),
                                      in_stock=not any(w in stock.lower() for w in ("yoxdur", "bitib", "out of stock"))))
            except Exception as e:   # bir kartdakı xəta bütün scraping-i dayandırmasın
                res.warnings.append(f"kart oxunmadı: {type(e).__name__}")
    finally:
        driver.quit()
    return res
