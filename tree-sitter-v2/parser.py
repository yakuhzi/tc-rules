import itertools
import os
import textwrap
from tree_sitter import Language, Parser
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import re
import json

Language.build_library(
    # Store the library in the `build` directory
    'build/my-languages.so',

    # Include one or more languages
    [
        'tree-sitter/tree-sitter-python',
        'tree-sitter/tree-sitter-java',
        'tree-sitter/tree-sitter-cpp'
    ]
)

PY_LANGUAGE = Language('build/my-languages.so', 'python')
JV_LANGUAGE = Language('build/my-languages.so', 'java')
CPP_LANGUAGE = Language('build/my-languages.so', 'cpp')

PYTHON = "PYTHON"
JAVA = "JAVA"
CPP = "CPP"

types = ["int", "float", "double", "boolean", "bool"]

operators = [["==", "!=", ">=", "<=", ">", "<"], # comparison
            ["++", "+=", "+", "--", "-=","-", "//", "/=", "/", "%=", "%", "**", "*=", "*"], # arithmetic and assignment
            ["&&", "||", "!", "and", "or", "not"], # logical
            ["is not", "is"], # identity
            ["not in", "in"] # membership
            ]

files = ["simple", "if", "while"]

"""Create Parser"""
parser_py = Parser()
parser_py.set_language(PY_LANGUAGE)

parser_jv = Parser()
parser_jv.set_language(JV_LANGUAGE)

parser_cpp = Parser()
parser_cpp.set_language(CPP_LANGUAGE)


class RuleSet:
    def __init__(self):
        if not os.path.isfile("codegen_sources/scripts/tc-rules/tree-sitter-v2/rules.json"):
            self.rules = {}
        else:
            with open("codegen_sources/scripts/tc-rules/tree-sitter-v2/rules.json") as file:
                self.rules = json.load(file)
                print(f"Loading {len(self.rules)} rules ... Done ...")    
        
        with open("codegen_sources/scripts/tc-rules/tree-sitter-v2/keywords.json") as file:
            self.keywords = json.load(file)

        if not os.path.isfile("codegen_sources/scripts/tc-rules/tree-sitter-v2/tree-keywords.txt"):
            self.tree_keywords = []
        else:
            with open("codegen_sources/scripts/tc-rules/tree-sitter-v2/tree-keywords.txt") as file:
                self.tree_keywords = file.read().split(",")
                print(f"Loading {len(self.tree_keywords)} keywords for parse tree ... Done ...")  

    def save_rules(self):
        with open("codegen_sources/scripts/tc-rules/tree-sitter-v2/rules.json", "a+") as file:
            file.truncate(0)
            file.seek(0)
            json.dump(self.rules, file, indent=4)


    def save_keywords(self):
        with open("codegen_sources/scripts/tc-rules/tree-sitter-v2/tree-keywords.txt", "a+") as file:
            file.truncate(0)
            file.seek(0)
            length = len(self.tree_keywords)-1
            for i, keyword in enumerate(self.tree_keywords):
                if i == length:
                    file.write(keyword)
                else:
                    file.write(keyword+",")

    def check_for_keyword(self, parse_tree_sexp, parse_tree):
        if "ERROR" in parse_tree_sexp:
            return "ERROR"
        for keyword in self.tree_keywords:
            if keyword in parse_tree_sexp:
                return keyword
        # else add it
        root_node = parse_tree.root_node
        if root_node.children:
            self.tree_keywords.append(root_node.children[0].type)
            return str(root_node.children[0].type)
        else:
            return ""


    # return generic expression for code line input
    def create_generic_expression(self, code, language=CPP.lower()):
        generic_code = code

        in_keywords, names = extract_name(self, code)
        if in_keywords:
            return self.keywords[names][language]
        if names:
            for name in names:
                generic_code = re.sub(r"\b{}\b".format(name), "name", generic_code)

        values = extract_value(code)
        if values:
            for value in values:
                generic_code = generic_code.replace(value[0], "value", value[1])
        
        type = extract_type(code)
        if type:
            generic_code = re.sub(r"\b{}\b".format(type), "type", generic_code)

        operators = extract_operator(code)
        if operators:
            for operator in operators:
                generic_code = generic_code.replace(operator, "operator")

        #print(generic_code, code)
        return generic_code if len(generic_code) - len(generic_code.lstrip()) == 0 else None


    def extend_rule(self, cpp, jv, py, key):
        generic_cpp = self.create_generic_expression(cpp)
        generic_jv = self.create_generic_expression(jv, JAVA.lower())
        generic_py = self.create_generic_expression(py, PYTHON.lower())

        if generic_cpp and generic_jv and generic_py:
            flag = False

            for list in self.rules[key]:
                if generic_cpp in list:
                    flag = True
                    break
            if flag == False:
                self.rules[key].append([generic_cpp, generic_jv, generic_py])
            #print(self.rules)


    def add_rule(self, cpp, jv, py, key):
        generic_cpp = self.create_generic_expression(cpp)
        generic_jv = self.create_generic_expression(jv, JAVA.lower())
        generic_py = self.create_generic_expression(py, PYTHON.lower())

        if generic_cpp and generic_jv and generic_py:
            self.rules.update({key: [[generic_cpp, generic_jv, generic_py]]})
        #print(self.rules)


    # for now used for if_statement
    def check_statement(self, keyword, cpp_file, py_file, jv_file): # , line_jv, jv):    
        generic_statements = []

        # CPP
        with open(cpp_file, 'r+') as cpp:
            lines_cpp = cpp.readlines()
        for line_cpp in lines_cpp:
            tree_sexp, tree = create_parse_tree(line_cpp, CPP)
            if self.check_for_keyword(tree_sexp, tree) == keyword:
                generic_statements.append(create_generic_statement(lines_cpp, line_cpp, CPP)[0])

        # JAVA
        #generic_statements.append(create_generic_statement(jv, line_jv)[0])
        with open(jv_file, 'r+') as jv:
            lines_jv = jv.readlines()
        for line_jv in lines_jv:
            tree_sexp, tree = create_parse_tree(line_jv, JAVA)
            if self.check_for_keyword(tree_sexp, tree) == keyword:
                generic_statements.append(create_generic_statement(lines_jv, line_jv, JAVA)[0])

        # PYTHON
        with open(py_file, 'r+') as py:
            lines_py = py.readlines()
        for line_py in lines_py:
            tree_sexp, tree = create_parse_tree(line_py, PYTHON)
            if self.check_for_keyword(tree_sexp, tree) == keyword:
                generic_statements.append(create_generic_statement(lines_py, line_py, PYTHON)[0])
        #print(generic_statements)
        return generic_statements


    def derive_rules(self, files):
        for file in files:
            with open("data/"+file+".py", 'r') as py, open("data/"+file+".java", 'r') as jv, open("data/"+file+".cpp", "r") as cpp: # use parallel corpus
                for line_py, line_jv, line_cpp in zip(py, jv, cpp):
                    tree_sexp, tree = create_parse_tree(line_jv, JAVA)
                    keyword = self.check_for_keyword(tree_sexp, tree)

                    if keyword in ["if_statement", "while_statement"]:
                        if keyword not in self.rules.keys():
                            self.rules.update({keyword: [self.check_statement(keyword, "data/"+file+".cpp", "data/"+file+".py", "data/"+file+".java")]})
                    
                    elif keyword and keyword != "ERROR":
                        best_match = process.extractOne(keyword, self.rules.keys(), scorer=fuzz.partial_ratio)
                        if not best_match or best_match[-1] != 100:
                            self.add_rule(line_cpp, line_jv, line_py, keyword)
                        else:
                            self.extend_rule(line_cpp, line_jv, line_py, best_match[0])


    # translate given input file
    def translate(self, file_name, language):
        translations = []
        with open("data/"+file_name, 'r+') as file:
            lines = file.readlines()
        j = -1 
        for i,line in enumerate(lines):
            if j >= i:
                continue

            tree_sexp, tree = create_parse_tree(line, language)
            keyword = self.check_for_keyword(tree_sexp, tree)
            if keyword in ["if_statement", "while_statement"] and keyword in self.rules.keys():
                generic_statement, statement, j = create_generic_statement(lines, line, language)
                if generic_statement in self.rules[keyword][0]:
                    translations.append(self.transform_statement(self.rules[keyword][0], statement, language))

            elif keyword and keyword != "ERROR":
                best_match = process.extractOne(keyword, self.rules.keys(), scorer=fuzz.partial_ratio)
                if best_match[-1] == 100:
                    flag = False
                    for list in self.rules[best_match[0]]:
                        if self.create_generic_expression(line,language.lower()) in list:
                            translations.append(self.transform(list, line))
                            flag = True
                    if not flag:
                        print(f"No appropriate transformation for {best_match[0], self.create_generic_expression(line, language.lower())} was found in the database...")
                else:
                    print(f"No appropriate rule for {keyword} was found in the database...")
        return translations


    # translate single code line
    def translate_line(self, code_input, language):
        tree_sexp, tree = create_parse_tree(code_input, language)
        keyword = self.check_for_keyword(tree_sexp, tree)
        if keyword:
            best_match = process.extractOne(keyword, self.rules.keys(), scorer=fuzz.partial_ratio)
            if best_match[-1] == 100:
                for list in self.rules[best_match[0]]:
                    if self.create_generic_expression(code_input, language.lower()) in list:
                        return self.transform(list, code_input)
        return None


    # translate the generic expressions for the if_statement and while_statement using the input statement
    def transform_statement(self, generic_expressions, statement, language):
        translations = []

        for i, entry in enumerate(generic_expressions):
            if language in [CPP,JAVA]:
                condition = re.findall('\(([^"]*)\) \{', statement)[0]
                block = re.findall('\{([^}]+)\}', statement)[0].split("\n")
            else: 
                condition = re.findall('(if|while) (.*):', statement)[0][1]
                block = statement[statement.index(":")+1:].split("\n")

            block = [textwrap.dedent(item)+"\n" for item in block if item]
            entry = entry.replace("@", condition, 1)
            # for each line in block --> translation via rules
            if "@" in entry:
                for line in block:
                    code_line_translated = self.translate_line(line, language)
                    if code_line_translated:
                        entry = re.sub('@', code_line_translated[i]+"    @", entry)
            entry = re.sub('\n    @', '', entry)

            translations.append(entry)
        #print(translations)
        return translations


    # translate the generic expressions for single line using the input code 
    def transform(self, generic_expressions, code):
        translations = []

        tokens = code.split()
        keywords = []
        tokens_to_replace = []
        for token in tokens:
            best_match = process.extractOne(token, self.keywords.keys(), scorer=fuzz.ratio)
            if best_match[-1] >= 70:
                keywords.append(self.keywords[best_match[0]])
                tokens_to_replace.append(token)
        
        for i, entry in enumerate(generic_expressions):
            updated_input = code
            if keywords:
                for index, token in enumerate(tokens_to_replace):
                    if i == 0 and token != keywords[index]["cpp"]:
                        updated_input = re.sub(token, keywords[index]["cpp"], updated_input)
                    elif i == 1 and token != keywords[index]["java"]:
                        updated_input = re.sub(token, keywords[index]["java"], updated_input)
                    elif token != keywords[index]["python"]:
                        updated_input = re.sub(token, keywords[index]["python"], updated_input)

            values = extract_value(updated_input)
            if values:
                for value in values:
                    entry = entry.replace("value", value[0], value[1])           
        
            in_keywords, names = extract_name(self, updated_input)
            if in_keywords:
                if "@" in entry:
                    string = re.findall('\(([^\()]*)\)', code) # print argument in java and python
                    if not string:
                        string = re.findall('<<([^<]*);', code) # print argument in cpp
                    for s in string:
                        entry = re.sub('@', s+"@", entry)
                    entry = re.sub('@', '', entry)
            if names:
                for name in names:
                    entry = entry.replace("name", name, 1)

            type = extract_type(updated_input)
            if type == "bool":
                best_match = process.extractOne("bool", self.keywords.keys(), scorer=fuzz.ratio)
                if best_match[-1] >= 70:
                    if i == 0:
                        entry = re.sub("type", self.keywords[best_match[0]]["cpp"], entry)
                    elif i == 1:
                        entry = re.sub("type", self.keywords[best_match[0]]["java"], entry)
                    else:
                        entry = re.sub("type", self.keywords[best_match[0]]["python"], entry)
            elif type:
                entry = entry.replace("type", type) 
                    
            operators = extract_operator(updated_input)
            if operators:
                for operator in operators:
                    entry = entry.replace("operator", operator)

            translations.append(entry)

        return translations


def create_parse_tree(input_code, input_language):
    if input_language == "PYTHON":
        return parser_py.parse(bytes(input_code, "utf-8")).root_node.sexp(), parser_py.parse(bytes(input_code, "utf-8"))
    elif input_language == "JAVA":
        return parser_jv.parse(bytes(input_code, "utf-8")).root_node.sexp(), parser_jv.parse(bytes(input_code, "utf-8"))
    elif input_language == "CPP":
        return parser_cpp.parse(bytes(input_code, "utf-8")).root_node.sexp(), parser_cpp.parse(bytes(input_code, "utf-8"))


# create generic expression for if_statement and while_statement
def create_generic_statement(lines, line, language=JAVA):
    i = lines.index(line)
    lines = [l for l in lines[i+1:]]
    statement = line
    j = 0
    if language in [JAVA, CPP]:
        statement += lines[j]
        while "MISSING" in create_parse_tree(statement, language)[0]:
            j += 1
            statement += lines[j]

        gen_statement = line
        gen_statement += lines[j-1] + lines[j]
        gen_statement = re.sub('if \(([^"]*)\)', 'if (@)', gen_statement)
        gen_statement = re.sub('while \(([^"]*)\)', 'while (@)', gen_statement)
        block = re.findall('\{([^}]+)\}', statement)[0].split("\n")
        block = [textwrap.dedent(item) for item in block if item]
        gen_statement = gen_statement.replace(block[-1], '@')
        return gen_statement, statement, j+1+i

    else:
        while j < len(lines) and lines[j] != "\n" and len(lines[j]) - len(lines[j].lstrip()) != 0: # indent
            statement += lines[j]
            j += 1
        
        gen_statement = line
        gen_statement += lines[j-1]
        gen_statement = gen_statement.replace(textwrap.dedent(lines[j-1]), '@\n')

        gen_statement = re.sub('if (.*):', 'if @:', gen_statement)
        gen_statement = re.sub('while (.*):', 'while @:', gen_statement)
        return gen_statement, statement, j+i


def extract_type(input_string):
    input = input_string.split()
    for type in types:
        if type in input:
            return type

    numbers = extract_value(input_string)
    if numbers and len(numbers) == 1:
        if numbers[0][0] in ["true", "false", "True", "False"]:
            return "bool"
        if re.search(r"\.", numbers[0][0]) is None:
            return "int"
        elif len(numbers[0][0]) < 9:
            return "float"  # 6-7 significant digits
        return "double"  # 15-16 significant digits

    if numbers:  # more than one
        flag_float, flag_double = False, False
        for number in numbers:
            if number in ["true", "false", "True", "False"]:
                return "bool"
            if re.search(r"\.", number[0]) is None:
                continue  # int
            elif len(number[0]) < 9:
                flag_float = True  # 6-7 significant digits
            else:
                flag_double = True  # 15-16 significant digits
        if flag_double:
            return "double"
        if flag_float:
            return "float"
        return "int"
    return None


def extract_value(input_string):
    numbers = re.findall(r'true|false|True|False', input_string)
    string = re.sub('([a-z,A-Z]+[_]*[a-z,A-Z,0-9]*)*', '', input_string)
    numbers.extend(re.findall(r'\d+(?:\.\d+)?', string))
    if numbers:
        #print("values",[(number, numbers.count(number)) for number in numbers])
        return [(number, numbers.count(number)) for number in numbers]


def extract_name(self, input_string):
    string = re.sub('true|false|True|False', '', input_string)
    string = re.sub('\(([^\()]*)\)', '@', string) # print arg in java and python
    string = re.sub('<<([^<]*);', '@', string) # print arg in cpp
    temp = string.split()
    for t in temp:
        if t in types:
            temp.remove(t)
        for op_list in operators:
            if t in op_list:
                temp.remove(t)
    string = " ".join(temp)
    best_match = process.extractOne(string, self.keywords.keys(), scorer=fuzz.token_set_ratio)
    if best_match[-1] >= 45:
        return True, best_match[0]
    names = re.findall('([a-z,A-Z]+[_]*[a-z,A-Z,0-9]*)*', string)
    return False, [name for name in names if name and name not in types]


def extract_operator(input_string):
    op = []
    for i, group in enumerate(operators):
        for operator in group:
            if operator in input_string:
                #print("op", operator)
                op.append(operator)
    return op if op else None
