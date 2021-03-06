import logging
import yaml
import os
import re

from trello import TrelloClient
from leankit import LeankitKanban
from kanban_flow import KanbanFlowBoard


class LeanKit:
    kb = None
    log = logging.getLogger(__name__)

    def __init__(self):
        self.config = load_config("config/leankit-config.yaml")
        board_id = self.config['board_id']
        self.kb = LeankitKanban(self.config['account'], self.config['email'],
                                self.config['password'])
        self.log.debug("Connecting to Leankit board {0}".format(board_id))
        self.board = self.kb.get_board(board_id=board_id)

    def find_completed_card_ids(self):
        lanes = self.config['completed_lanes']
        card_ids = self.board.cards_with_external_ids(lanes)
        self.log.debug("Found {0} cards in completed lanes".format(len(card_ids)))
        card_ids = card_ids + self.find_completed_cards_in_taskboards()
        self.log.debug("Completed cards with external ids: {0}".format(card_ids))
        return card_ids

    def find_completed_cards_in_taskboards(self):
        taskboard_cards = self.board.done_taskboard_cards()
        self.log.debug("Found {0} completed cards in taskboards".format(len(taskboard_cards)))
        return taskboard_cards

    def card_exists(self, identifier):
        return identifier in self.board.external_ids

    def add_cards(self, cards):
        return self.board.add_cards(cards)


class KanbanFlow:
    kb = None
    log = logging.getLogger(__name__)

    def __init__(self):
        self.config = load_config("config/kanbanflow-config.yaml")

        token = self.config['token']
        default_drop_lane = self.config['default_drop_lane']
        types = self.config['card_types']
        completed_columns = self.config['completed_lanes']

        self.kb = KanbanFlowBoard(token, default_drop_lane, types, completed_columns)

    def find_completed_card_ids(self):
        return self.kb.completed_tasks

    def card_exists(self, identifier):
        return identifier in self.kb.all_tasks

    def add_cards(self, cards):
        cards_added = self.kb.create_tasks(cards)
        self.log.debug("Made {0} API requests in this session".format(self.kb.api_requests))
        return cards_added


class Trello:
    COMMENT_PREFIX = "external_id="
    log = logging.getLogger(__name__)

    def __init__(self):
        self.config = load_config("config/trello-config.yaml")
        self.cards_with_external_ids = []
        self.labels = {}

        app_key = self.config['app_key']
        token = self.config['token']
        board_id = self.config['board_id']

        self.board = TrelloClient(api_key=app_key, token=token).get_board(board_id)
        self.classify_board()
        self.log.debug("Connecting to Trello board {0}".format(board_id))

    def classify_board(self):
        cards = self.board.all_cards()
        self.log.debug("Classifying Trello board, contains {0} cards".format(len(cards)))

        for label in self.board.get_labels():
            self.labels[label.name] = label

        for card in cards:
            if card.closed:
                self.log.debug("Ignoring closed card {0} ({1})".format(card.name, card.id))
            else:
                self.log.debug("Looking for external id in {0}".format(card.name))
                self.cards_with_external_ids.append(Trello.get_external_id(card))

    @staticmethod
    def get_external_id(card):
        external_id = None
        card.fetch()
        comments = card.comments
        if comments:
            for comment in comments:
                text = comment['data']['text']
                if Trello.COMMENT_PREFIX in text:
                    external_id = re.sub(Trello.COMMENT_PREFIX, '', text)
        return external_id

    def clear_board(self):
        for card in self.board.all_cards():
            self.log.debug("Deleting {0} {1}".format(card.name, card.id))
            card.delete()

    def card_exists(self, identifier):
        return identifier in self.cards_with_external_ids

    def add_cards(self, cards):
        default_list = self.board.get_list(self.config['default_list'])
        self.log.debug("Adding {0} cards to lane {1} ({2})".format(len(cards), default_list.name, default_list.id))
        for card in cards:
            name = card['name']
            identifier = card['identifier']
            card_type = card['type']
            note = card['note']

            card = default_list.add_card(name)
            if note is not None:
                card.set_description(note)
            card.comment("{0}{1}".format(Trello.COMMENT_PREFIX, identifier))

            try:
                card.add_label(self.labels[card_type])
                self.log.debug("Creating card with details: name={0} id={1} type={2}".
                               format(name, identifier, card_type))
            except KeyError:
                self.log.debug("Can't find card type {0} configured in Trello".format(card_type))
                self.log.debug("Creating card with details: name={0} id={1} type=default".
                               format(name, identifier))

    def find_completed_card_ids(self):
        completed_lists = self.config['completed_lists']
        self.log.debug("Looking for cards in completed lanes: {0}".format(completed_lists))
        cards = []

        for list_id in completed_lists:
            completed_list = self.board.get_list(list_id)
            cards.extend([Trello.get_external_id(card) for card in completed_list.list_cards()])

        # [cards.extend([card.external_card_id for card in self.trello.lane.get(lane).cards
        #                if len(card.external_card_id) > 1]) for lane in lanes]
        self.log.debug("Found {0} completed cards on the board".format(len(cards)))
        self.log.debug("External ids: {0}".format(cards))
        return cards


def load_config(path):
    path = "{0}/{1}".format(os.getcwd(), path)
    logging.debug("Loading config file {0}".format(path))
    f = open(path)
    config = yaml.safe_load(f)
    f.close()
    return config

if __name__ == '__main__':
    board = Trello()
    board.clear_board()
