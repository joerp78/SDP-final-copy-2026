import json 

with open('test_data.json', 'r') as file:
    data = json.load(file)

print(data)
print(data[0]['epc'])
