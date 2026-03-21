package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Modifier;
import java.util.Collections;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CSVRecord_12_2Test {

    @Test
    @Timeout(8000)
    void testToString_withNonEmptyValues() throws Exception {
        // Prepare values array
        String[] values = new String[] { "one", "two", "three" };
        // Prepare mapping (can be empty as toString does not use it)
        Map<String, Integer> mapping = Collections.emptyMap();
        // Prepare other constructor args
        String comment = "comment";
        long recordNumber = 123L;

        CSVRecord record = createCSVRecord(values, mapping, comment, recordNumber);

        String expected = "[one, two, three]";
        String actual = record.toString();

        assertEquals(expected, actual);
    }

    @Test
    @Timeout(8000)
    void testToString_withEmptyValues() throws Exception {
        String[] values = new String[0];
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 0L;

        CSVRecord record = createCSVRecord(values, mapping, comment, recordNumber);

        String expected = "[]";
        String actual = record.toString();

        assertEquals(expected, actual);
    }

    @Test
    @Timeout(8000)
    void testToString_withNullValuesArray() throws Exception {
        // We try to create CSVRecord with values field set to null via reflection
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 0L;

        CSVRecord record = createCSVRecord(new String[] {}, mapping, comment, recordNumber);

        // Set private final field 'values' to null using reflection
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier from the field 'values'
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~Modifier.FINAL);

        valuesField.set(record, null);

        // toString() should handle null values gracefully, but as per code it calls Arrays.toString(values)
        // Arrays.toString(null) returns "null"
        String expected = "null";
        String actual = record.toString();

        assertEquals(expected, actual);
    }

    // Utility method to instantiate CSVRecord via its package-private constructor using reflection
    private CSVRecord createCSVRecord(String[] values, Map<String, Integer> mapping, String comment, long recordNumber)
            throws NoSuchMethodException, IllegalAccessException, InvocationTargetException, InstantiationException {
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        return constructor.newInstance(values, mapping, comment, recordNumber);
    }
}