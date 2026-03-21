package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_8_4Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;
    private String comment;
    private long recordNumber;

    @BeforeEach
    void setUp() {
        values = new String[] {"value1", "value2", "value3"};
        mapping = Collections.singletonMap("key1", 0);
        comment = "comment";
        recordNumber = 123L;
        csvRecord = new CSVRecord(values, mapping, comment, recordNumber);
    }

    @Test
    @Timeout(8000)
    void testValuesMethod() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException {
        Method valuesMethod = CSVRecord.class.getDeclaredMethod("values");
        valuesMethod.setAccessible(true);
        String[] returnedValues = (String[]) valuesMethod.invoke(csvRecord);
        assertArrayEquals(values, returnedValues);
    }

    @Test
    @Timeout(8000)
    void testValuesMethodReturnsEmptyArrayWhenValuesNull() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException, NoSuchFieldException {
        CSVRecord recordWithNullValues = new CSVRecord(new String[]{"dummy"}, mapping, comment, recordNumber);
        // Set the private final field 'values' to null using reflection
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier from the field 'values'
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~java.lang.reflect.Modifier.FINAL);

        valuesField.set(recordWithNullValues, null);

        Method valuesMethod = CSVRecord.class.getDeclaredMethod("values");
        valuesMethod.setAccessible(true);
        String[] returnedValues = (String[]) valuesMethod.invoke(recordWithNullValues);
        assertNotNull(returnedValues);
        assertEquals(0, returnedValues.length);
    }

}