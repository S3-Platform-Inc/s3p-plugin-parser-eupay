import dateparser
from datetime import datetime, date
import time

from s3p_sdk.plugin.payloads.parsers import S3PParserBase
from s3p_sdk.types import S3PRefer, S3PDocument, S3PPlugin
from selenium.common import NoSuchElementException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait


class EUPay(S3PParserBase):
    """
    A Parser payload that uses S3P Parser base class.
    """

    HOST = 'https://www.europeanpaymentscouncil.eu/search'

    def __init__(self, refer: S3PRefer, plugin: S3PPlugin, web_driver: WebDriver, max_count_documents: int = None,
                 last_document: S3PDocument = None):
        super().__init__(refer, plugin, max_count_documents, last_document)

        # Тут должны быть инициализированы свойства, характерные для этого парсера. Например: WebDriver
        self._driver = web_driver
        self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            'source': '''
                                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                          '''
        })
        self._wait = WebDriverWait(self._driver, timeout=20)

    """
    Класс парсера плагина SPP

    :warning Все необходимое для работы парсера должно находится внутри этого класса

    :_content_document: Это список объектов документа. При старте класса этот список должен обнулиться,
                        а затем по мере обработки источника - заполняться.


    """

    def _parse(self):
        """
        Метод, занимающийся парсингом. Он добавляет в _content_document документы, которые получилось обработать
        :return:
        :rtype:
        """
        # HOST - это главная ссылка на источник, по которому будет "бегать" парсер
        self.logger.debug(F"Parser enter to {self.HOST}")

        for page_url in self._encounter_pages():
            for doc in self._collect_docs(page_url):
                self._initial_access_source(doc.link, 3)
                if len(self._driver.find_elements(By.CLASS_NAME, 'content-container-details')) > 0:
                    try:
                        doc_text = self._driver.find_element(By.CLASS_NAME, 'content-container-details').find_element(
                            By.TAG_NAME, 'p').text
                    except:
                        doc_text = self._driver.find_element(By.CLASS_NAME, 'content-container-details').text
                elif len(self._driver.find_elements(By.CLASS_NAME, 'col-md-6')) > 0:
                    doc_text = self._driver.find_element(By.CLASS_NAME, 'col-md-6').text
                else:
                    doc_text = self._driver.find_element(By.TAG_NAME, 'article').find_element(By.CLASS_NAME,
                                                                                              'content').text
                doc.text = doc_text
                doc.load_date = datetime.now()
                doc.abstract = None

                self._find(doc)

    def _encounter_pages(self) -> str:
        _base = self.HOST
        _params = '?page='
        page = 0
        while True:
            url = _base + _params + str(page)
            page += 1
            yield url

    def _initial_access_source(self, url: str, delay: int = 2):
        self._driver.get(url)
        self.logger.debug('Entered on web page ' + url)
        time.sleep(delay)
        self._agree_cookie_pass()

    def _collect_docs(self, url: str) -> list[S3PDocument]:
        try:
            self._initial_access_source(url)
            self._wait.until(ec.presence_of_all_elements_located((By.CLASS_NAME, 'view-content')))
        except Exception as e:
            raise NoSuchElementException() from e

        links = []
        try:
            articles = self._driver.find_elements(By.TAG_NAME, 'article')
        except Exception as e:
            raise NoSuchElementException('list is empty') from e
        else:
            for i, el in enumerate(articles):
                web_link = None
                try:
                    try:
                        _title = el.find_element(By.CLASS_NAME, 'kb-title')
                        title_text = _title.text
                    except:
                        _title = el.find_element(By.CLASS_NAME, 'well').find_element(By.TAG_NAME, 'h2')
                        title_text = _title.text

                    web_link = _title.find_element(By.TAG_NAME, 'a').get_attribute('href')

                    try:
                        if len(el.find_elements(By.CLASS_NAME, 'kb-type')) > 0:
                            doc_type = el.find_element(By.CLASS_NAME, 'kb-type').text
                        elif len(el.find_elements(By.CLASS_NAME, 'news-type')) > 0:
                            doc_type = el.find_element(By.CLASS_NAME, 'news-type').text
                        elif len(el.find_elements(By.CLASS_NAME, 'label-alt')) > 0:
                            doc_type = el.find_element(By.CLASS_NAME, 'label-alt').text
                        else:
                            doc_type = None
                    except:
                        doc_type = None
                    try:
                        if len(el.find_elements(By.CLASS_NAME, 'kb-intro')) > 0:
                            date_text = el.find_element(By.CLASS_NAME, 'kb-intro').find_element(By.CLASS_NAME,
                                                                                                'date').text
                        elif len(el.find_elements(By.CLASS_NAME, 'field--created')) > 0:
                            date_text = el.find_element(By.CLASS_NAME, 'field--created').text
                        else:
                            date_text = datetime.strftime(date(2000, 1, 1), __format='%Y-%m-%d')
                        parsed_date = dateparser.parse(date_text)
                    except:
                        continue

                    try:
                        tags = el.find_element(By.CLASS_NAME, 'kb-tags').text
                    except:
                        tags = None

                except Exception as e:
                    self.logger.debug(NoSuchElementException(
                        'Страница не открывается или ошибка получения обязательных полей. URL: ' + str(web_link)))
                    continue
                else:
                    _doc = S3PDocument(None, title_text, None, None, web_link, None, {
                        'doc_type': doc_type,
                        'tags': tags,
                    }, parsed_date, None)
                    links.append(_doc)
        return links

    def _agree_cookie_pass(self):
        """
        Метод прожимает кнопку agree на модальном окне
        """
        cookie_agree_xpath = '//button[text() = \'Accept All Cookies\']'

        try:
            cookie_button = self._driver.find_element(By.XPATH, cookie_agree_xpath)
            if WebDriverWait(self._driver, 5).until(ec.element_to_be_clickable(cookie_button)):
                cookie_button.click()
                self.logger.debug(F"Parser pass cookie modal on page: {self._driver.current_url}")
        except NoSuchElementException as e:
            self.logger.debug(f'modal agree not found on page: {self._driver.current_url}')
