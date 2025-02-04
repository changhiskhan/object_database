#   Copyright 2017-2019 object_database Authors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from object_database.web import cells as cells
from object_database.web.CellsTestPage import CellsTestPage


class BasicModal(CellsTestPage):
    def cell(self):
        isShowing = cells.Slot(False)

        button = cells.Button("Toggle Modal", lambda: isShowing.set(True))

        modal = cells.Subscribed(
            lambda: cells.Modal(
                cells.Text("Modal Body")
                + cells.Right(cells.Button("Close", lambda: isShowing.set(False))),
                onEsc=lambda: isShowing.set(False),
                onEnter=lambda: isShowing.set(False),
            )
            if isShowing.get()
            else None
        )

        return cells.Card(button + modal)

    def text(self):
        return (
            "When you click Toggle, you should see a basic modal appear "
            "and it should be closable"
        )


class ModalWithUpdateField(CellsTestPage):
    def cell(self):
        isShowing = cells.Slot(False)

        committedContent = cells.Slot("Some Text")
        editContent = cells.Slot("Some Text")

        button = cells.Button("Open Modal", lambda: isShowing.set(True))

        textDisplay = cells.Subscribed(lambda: cells.Text(committedContent.get()))

        def onOK():
            committedContent.set(editContent.get())
            isShowing.set(False)

        def onCancel():
            editContent.set(committedContent.get())

        textBox = cells.SingleLineTextBox(editContent, onEnter=onOK, onEsc=onCancel)

        def showingChanged(old, new, reason):
            if new and not old:
                textBox.focus()

        isShowing.addListener(showingChanged)

        modal = cells.ButtonModal(isShowing, "Text Updater", textBox, ok=onOK, cancel=onCancel)

        return cells.Card(button + textDisplay + modal)

    def text(self):
        return (
            "You should see a button that lets you edit the "
            "'Some Text' text in a modal popup or cancel it"
        )


def test_basic_modal(headless_browser):
    headless_browser.load_demo_page(BasicModal)

    button_query = '[data-cell-type="Button"]'
    button = headless_browser.find_by_css(button_query)

    modal_query = ".modal-cell-show"

    # Clicking on the button causes the modal to appear
    button.click()
    headless_browser.wait(2).until(
        headless_browser.expect.visibility_of_element_located(
            (headless_browser.by.CSS_SELECTOR, modal_query)
        )
    )

    # Clicking on the modal's "close" button, makes the bodal disappear
    modal_button_query = modal_query + ' [data-cell-type="Button"]'
    close_button = headless_browser.find_by_css(modal_button_query)
    assert close_button.text == "Close"

    close_button.click()
    headless_browser.wait(2).until(
        headless_browser.expect.invisibility_of_element_located(
            (headless_browser.by.CSS_SELECTOR, modal_query)
        )
    )


def test_modal_with_update_field(headless_browser):
    """ Test Modal with update field.

    - modal is initially hidden
    - read the text on the card
    - click on the button to make the modal appear
    - check that the SingleLineTextBox is in focus
    - check that the text in the SingleLineTextBox matches the text on the card
    - modify the text in the SingleLineTextBox
    - click on the modal button to hide the modal and update the card text
    """
    headless_browser.load_demo_page(ModalWithUpdateField)
    slot_text = "Some Text"

    button_query = '[data-cell-type="Button"]'
    button = headless_browser.find_by_css(button_query)
    assert button.text == "Open Modal"

    # The modal is initially hidden
    modal_query = ".modal-cell-show"

    # Read the text on the card
    text_query = '.button-holder + [data-cell-type="Text"]'  # + means get sibling
    text = headless_browser.find_by_css(text_query)
    assert text.text == slot_text

    # Clicking on the button causes the modal to appear
    button.click()
    headless_browser.wait(2).until(
        headless_browser.expect.visibility_of_element_located(
            (headless_browser.by.CSS_SELECTOR, modal_query)
        )
    )

    # Check that the SLTB is in focus (it should be after showing)
    modal_text_query = modal_query + ' [data-cell-type="SingleLineTextBox"]'
    text_box = headless_browser.find_by_css(modal_text_query)
    assert text_box == headless_browser.webdriver.switch_to.active_element

    # the text in the SingleLineTextBox matches the text on the card
    assert text_box.get_attribute("value") == slot_text

    # modify the text in the SingleLineTextBox
    from selenium.webdriver.common.keys import Keys

    text_box.send_keys((len(slot_text) * Keys.DELETE) + "final text")
    slot_text = "final text"
    assert text_box.get_attribute("value") == slot_text

    # click on the modal button to hide the modal and update the card text
    modal_button_query = modal_query + ' [data-cell-type="Button"]'
    modal_button = headless_browser.find_by_css(modal_button_query)
    assert modal_button.text == "OK"

    modal_button.click()

    headless_browser.wait(2).until(
        headless_browser.expect.invisibility_of_element_located(
            (headless_browser.by.CSS_SELECTOR, modal_query)
        )
    )

    text = headless_browser.find_by_css(text_query)
    assert text.text == slot_text


def test_modal_with_cancel_and_update_buttons(headless_browser):
    """ Test Modal with Update and Cancel Fields.

    - modal is initially hidden
    - read the text on the card
    - click on the button to make the modal appear
    - the text in the SingleLineTextBox matches the text on the card
    - modify the text in the SingleLineTextBox
        - clicking on the Cancel button makes the modal disappear without updating the card
        - clicking on the Update button makes the modal dissapear and updates the card
    """
    headless_browser.load_demo_page(ModalWithUpdateField)
    initial_text = "Some Text"
    slot_text = initial_text

    button_query = '[data-cell-type="Button"]'
    # The modal is initially hidden
    modal_query = ".modal-cell-show"

    # Read the text on the card
    text_query = '.button-holder + [data-cell-type="Text"]'  # + means get sibling
    text = headless_browser.find_by_css(text_query)
    assert text.text == slot_text

    # Clicking on the button causes the modal to appear
    def openModal():
        button = headless_browser.find_by_css(button_query)
        assert button.text == "Open Modal"

        button.click()
        headless_browser.wait(2).until(
            headless_browser.expect.visibility_of_element_located(
                (headless_browser.by.CSS_SELECTOR, modal_query)
            )
        )

    openModal()

    # the text in the SingleLineTextBox matches the text on the card
    modal_text_query = modal_query + ' [data-cell-type="SingleLineTextBox"]'

    def checkTextBox(expected_text):
        text_box = headless_browser.find_by_css(modal_text_query)
        assert text_box.get_attribute("value") == expected_text

    checkTextBox(slot_text)

    # modify the text in the SingleLineTextBox
    def modifyTextBox(new_text):
        text_box = headless_browser.find_by_css(modal_text_query)
        slot_text = text_box.get_attribute("value")

        from selenium.webdriver.common.keys import Keys

        text_box.send_keys(len(slot_text) * Keys.DELETE + new_text)
        assert text_box.get_attribute("value") == new_text
        return new_text

    slot_text = modifyTextBox("final text")

    # clicking on the "Cancel" button makes the modal disappear without updating the card
    def get_modal_buttons():
        modal_buttons_query = modal_query + ' [data-cell-type="Button"]'
        modal_buttons = headless_browser.find_by_css(modal_buttons_query, many=True)
        assert len(modal_buttons) == 2
        modal_buttons = {mb.text: mb for mb in modal_buttons}
        assert "Cancel" in modal_buttons
        assert "OK" in modal_buttons
        return modal_buttons

    def closeModal(button):
        get_modal_buttons()[button].click()
        headless_browser.wait(2).until(
            headless_browser.expect.invisibility_of_element_located(
                (headless_browser.by.CSS_SELECTOR, modal_query)
            )
        )

    closeModal("Cancel")

    text = headless_browser.find_by_css(text_query)
    assert text.text == initial_text
    slot_text = initial_text

    # clicking on the Update button makes the modal dissapear and updates the card
    openModal()
    checkTextBox(slot_text)
    slot_text = modifyTextBox("updated text")
    closeModal("OK")
    text = headless_browser.find_by_css(text_query)
    assert text.text == slot_text
