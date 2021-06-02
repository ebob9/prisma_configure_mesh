#!/usr/bin/env python
"""
Quick and dirty menu systems

github@ebob9.com

"""


def quick_menu(banner, list_line_format, choice_list):
    """
    Function
    :param banner: Text to display before menu
    :param list_line_format: Print'ing string with format spots for index + tuple values
    :param choice_list: List of tuple values that you want returned if selected (and printed)
    :return: Tuple that was selected.
    """
    # Setup menu
    invalid = True
    menu_int = -1

    # loop until valid
    while invalid:
        print(banner)

        for item_index, item_value in enumerate(choice_list):
            print(list_line_format.format(item_index+1, *item_value))

        menu_choice = input("\nChoose a Number or (Q)uit: ")

        if str(menu_choice).lower() in ['q']:
            # exit
            print("Exiting..")
            exit(0)

        # verify number entered
        try:
            menu_int = int(menu_choice)
            sanity = True
        except ValueError:
            sanity = False

        # validate number chosen
        if sanity and 1 <= menu_int <= len(choice_list):
            invalid = False
        else:
            print("Invalid input, needs to be between 1 and {0}.\n".format(len(choice_list)))

    # return the choice_list tuple that matches the entry.
    return choice_list[int(menu_int) - 1]


def quick_int_input(prompt, default_value, min=1, max=30):
    valid = False
    num_val = default_value
    while not valid:
        input_val = input(prompt + "[{0}]: ".format(default_value))

        if input_val == "":
            num_val = default_value
            valid = True
        else:
            try:
                num_val = int(input_val)
                if min <= num_val <= max:
                    valid = True
                else:
                    print("ERROR: must be between {0} and {1}.".format(min, max))
                    valid = False

            except ValueError:
                print("ERROR: must be a number.")
                valid = False

    return num_val


def quick_str_input(prompt, default_value):
    valid = False
    str_val = default_value
    while not valid:
        input_val = input(prompt + "[{0}]: ".format(default_value))

        if input_val == "":
            str_val = default_value
            valid = True
        else:
            try:
                str_val = str(input_val)
                valid = True

            except ValueError:
                print("ERROR: must be a number.")
                valid = False

    return str_val


def quick_confirm(prompt, default_value):
    valid = False
    value = default_value.lower()
    while not valid:
        input_val = input(prompt + "[{0}]: ".format(default_value))

        if input_val == "":
            value = default_value.lower()
            valid = True
        else:
            try:
                if input_val.lower() in ['y', 'n']:
                    value = input_val.lower()
                    valid = True
                else:
                    print("ERROR: enter 'Y' or 'N'.")
                    valid = False

            except ValueError:
                print("ERROR: enter 'Y' or 'N'.")
                valid = False

    return value
