import datetime
import random
import numpy as np
import csv
from sklearn.model_selection import train_test_split

import tensorflow as tf
from tensorflow.python.keras.datasets import cifar10, cifar100
from tensorflow.python.keras.utils import to_categorical

from encoder import ControllerManager, StateSpace
from manager import NetworkManager
from model import ModelGenerator

tf.enable_eager_execution()

B = 3  # number of blocks in each cell
K = 8  # number of children networks to train

MAX_EPOCHS = 2  # maximum number of epochs to train, adjust by xtpan from 5 to 2
BATCHSIZE = 512  # batchsize
CHILD_MODEL_LR = 0.001  # learning rate for the child models.
REGULARIZATION = 0  # regularization strength
CONTROLLER_CELLS = 100  # number of cells in RNN controller
RNN_TRAINING_EPOCHS = 2  # number of epochs to train the controller, adjust by xtpan from 10 to 2
RESTORE_CONTROLLER = False  # restore controller to continue training

operators = ['3x3 dconv', '5x5 dconv', '7x7 dconv',
             '1x7-7x1 conv', '3x3 maxpool', '3x3 avgpool']  # use the default set of operators, minus identity and conv 3x3
'''
operators = ['3x3 maxpool', '1x7-7x1 conv',]  # mini search space
'''

# construct a state space
state_space = StateSpace(B, input_lookback_depth=0, input_lookforward_depth=0,
                         operators=operators)

# print the state space being searched
state_space.print_state_space()
NUM_TRAILS = state_space.print_total_models(K)

x_train = []
y_train = []
x_test = []
y_test = []
label_size = 0
with open('nlp/train.dat', 'r') as f:
    for line in f:
        elements = line.strip('\r\n').split('\t')
        x_train.append(elements[0].split(','))
        y_train.append(elements[1])
        if int(elements[1]) > label_size:
            label_size = int(elements[1])
    f.close()
with open('nlp/val.dat', 'r') as f:
    for line in f:
        elements = line.strip('\r\n').split('\t')
        x_test.append(elements[0].split(','))
        y_test.append(elements[1])
        if int(elements[1]) > label_size:
            label_size = int(elements[1])
    f.close()
label_size += 1
x_train = np.asarray(x_train, dtype=np.float32)
y_train = np.asarray(y_train, dtype=np.int32)
x_test = np.asarray(x_test, dtype=np.float32)
y_test = np.asarray(y_test, dtype=np.int32)

y_train = np.reshape(y_train, newshape=[y_train.shape[0], 1])
y_train = to_categorical(y_train, num_classes=label_size)
y_test = np.reshape(y_test, newshape=[y_test.shape[0], 1])
y_test = to_categorical(y_test, num_classes=label_size)
x_train = np.reshape(x_train, newshape=[x_train.shape[0], x_train.shape[1], 1, 1])

dataset = [x_train, y_train, x_test, y_test]  # pack the dataset for the NetworkManager

# create the ControllerManager and build the internal policy network
controller = ControllerManager(state_space, B=B, K=K,
                               train_iterations=RNN_TRAINING_EPOCHS,
                               reg_param=REGULARIZATION,
                               controller_cells=CONTROLLER_CELLS,
                               restore_controller=RESTORE_CONTROLLER)

# create the Network Manager
manager = NetworkManager(dataset, epochs=MAX_EPOCHS, batchsize=BATCHSIZE)
print()

best_accu = 0.0
best_action_list = []
start_time = datetime.datetime.now()
print(start_time.strftime('%H:%M:%S'))
# train for number of trails
for trial in range(B):
    if trial == 0:
        k = None
    else:
        k = K

    actions = controller.get_actions(top_k=k)  # get all actions for the previous state

    rewards = []
    for t, action in enumerate(actions):
        # print the action probabilities
        state_space.print_actions(action)
        print("Model #%d / #%d" % (t + 1, len(actions)))
        print(" ", state_space.parse_state_space_list(action))

        # build a model, train and get reward and accuracy from the network manager
        reward = manager.get_rewards(ModelGenerator, state_space.parse_state_space_list(action))
        print("Final Accuracy : ", reward)
        if reward > best_accu:
            best_accu = reward
            best_action_list = action

        rewards.append(reward)
        print("\nFinished %d out of %d models ! \n" % (t + 1, len(actions)))

        # write the results of this trial into a file
        with open('train_history.csv', mode='a+', newline='') as f:
            data = [reward]
            data.extend(state_space.parse_state_space_list(action))
            writer = csv.writer(f)
            writer.writerow(data)

    loss = controller.train_step(rewards)
    print("Trial %d: ControllerManager loss : %0.6f" % (trial + 1, loss))

    controller.update_step()
    print()

end_time = datetime.datetime.now()
print(end_time.strftime('%H:%M:%S'))
print("Finished !")
print("Best accuracy is %f" % best_accu)
print("Best action list is ", state_space.parse_state_space_list(best_action_list))