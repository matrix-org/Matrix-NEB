from neb.plugins import Plugin
import collections
import random

class GuessNumberPlugin(Plugin):
    """Play a guess the number game.
    You have to guess what the number is in a certain number of attempts. You
    will be told information such as higher/lower than the guessed number.
    guessnumber new : Starts a new game.
    guessnumber hint : Get a hint for the number. Consumes an attempt.
    guessnumber guess <number> : Guess the number. Consumes an attempt.
    """
    name = "guessnumber"
    
    MAX_NUM = 100
    ATTEMPTS = 5
    
    def __init__(self, *args, **kwargs):
        super(Plugin, self).__init__(*args, **kwargs)
        self.games = {}
    
    
    def cmd_new(self, event):
        """Start a new game. 'guessnumber new'"""
        usr = event["user_id"]
        game_state = {
            "num": random.randint(0, GuessNumberPlugin.MAX_NUM),
            "attempts": 0
        }
        self.games[usr] = game_state
        return self._body("Created a new game. Guess what the chosen number is between 0-%s. You have %s attempts." % 
        (GuessNumberPlugin.MAX_NUM, GuessNumberPlugin.ATTEMPTS))
        
    def cmd_guess(self, event, num):
        """Make a guess. 'guessnumber guess <number>'"""
        usr = event["user_id"]
        
        if usr not in self.games:
            return self._body("You need to start a game first.")
        
        int_num = -1
        try:
            int_num = int(num)
        except:
            return self._body("That isn't a number.")
    
        target_num = self.games[usr]["num"]
        if int_num == target_num:
            self.games.pop(usr)
            return self._body("You win!")
        
        game_over = self._add_attempt(usr)
        
        if game_over:
            return game_over
        else:
            sign = "greater" if (target_num > int_num) else "less"
            return self._body("Nope. The number is %s than that." % sign)
        
    def cmd_hint(self, event):
        """Get a hint. 'guessnumber hint'"""
        # hints give a 50% reduction, e.g. between 0-50, even/odd, ends with 12345
        usr = event["user_id"]
        
        if usr not in self.games:
            return self._body("You need to start a game first.")
        
        num = self.games[usr]["num"]
        hint_pool = [self._odd_even, self._ends_with, self._between]
        hint_func = hint_pool[random.randint(1, len(hint_pool)) - 1]
        
        game_over = self._add_attempt(usr)
        
        if game_over:
            return game_over
        
        return self._body(hint_func(num))
        
    def _add_attempt(self, usr):
        self.games[usr]["attempts"] += 1
                
        if self.games[usr]["attempts"] >= GuessNumberPlugin.ATTEMPTS:
            res = self._body("Out of tries. The number was %s." % self.games[usr]["num"])
            self.games.pop(usr)
            return res
        
    def _between(self, num):
        half = GuessNumberPlugin.MAX_NUM / 2
        if num < half:
            return "The number is less than %s." % half
        else:
            return "The number is %s or greater." % half
        
    def _ends_with(self, num):
        actual = num % 10
        if actual < 5:
            return "The last digit is either 0, 1, 2, 3, 4."
        else:
            return "The last digit is either 5, 6, 7, 8, 9."
        
        
    def _odd_even(self, num):
        if num % 2 == 0:
            return "The number is even."
        else:
            return "The number is odd."
        
        
        
